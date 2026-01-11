"""
seed_generator_chatgpt.py
------------------------------------------------------------
OBJETIVO (para cursos)
Este script genera "seeds" (INSERTs) para poblar las tablas clave de una
aplicación de gestión de candidatos / postulaciones, a partir de entradas mínimas.
El modelo (ChatGPT vía OpenAI API) devuelve scripts SQL listos para ejecutar.

TABLAS (documentación resumida) - según tu diagrama y flujo "Banco de preguntas"
------------------------------------------------------------

1) question_pools
   - Propósito: Banco/Pool de preguntas por Habilidad Técnica + Nivel.
   - Campos típicos:
     * id (UUID/char36)
     * technical_skill (varchar)     -> "Habilidad Técnica"
     * level (enum/varchar)          -> BAJO/MEDIO/ALTO
     * question_quantity (int)       -> cantidad de preguntas a usar
     * total_certifiers (int)        -> cantidad de certificadores requeridos
     * is_active (tinyint/bool)
     * status (enum/varchar)
     * created_at, updated_at (timestamp)
   - Relaciones:
     * questions.question_pool_id -> question_pools.id
     * question_pools_certifiers.question_pool_id -> question_pools.id

2) questions
   - Propósito: Preguntas asociadas a un pool.
   - Campos típicos:
     * id (UUID)
     * question_pool_id (FK)
     * name (varchar/text)
     * options (json)                 -> opciones de respuesta
     * right_question_option_id (uuid) -> opción correcta
     * status (enum/varchar)
     * created_at, updated_at
   - Relaciones:
     * question_pool_id -> question_pools.id

3) question_pools_certifiers
   - Propósito: Asignación de certificadores a un pool (y su estado).
   - Campos típicos:
     * id (UUID)
     * question_pool_id (FK)
     * user_id (FK a users.id)  [si tu implementación lo tiene]
     * status (enum/varchar)
     * created_at, updated_at
   - Relaciones:
     * question_pool_id -> question_pools.id
     * user_id -> users.id (si existe)
     * question_validates.question_pool_certifier_id -> question_pools_certifiers.id

4) question_validates
   - Propósito: Workflow de validación de preguntas (pendiente/aceptado/rechazado).
   - Campos típicos:
     * id (UUID)
     * status (enum/varchar)
     * question_id (FK -> questions.id)
     * question_pool_certifier_id (FK -> question_pools_certifiers.id)
     * reason_rejection (text)
     * created_at, updated_at

5) job_positions
   - Propósito: Puestos/cargos a los que postulan (ej: "DBA Oracle", "Data Engineer").
   - Campos típicos:
     * id (UUID)
     * user_id (FK -> users.id) [owner/creador]
     * name (varchar)
     * soft_skills (json)
     * certifications (json) [si se guarda como JSON en tu modelo]
     * experience_level (enum)
     * is_archived (bool)
     * number_applicants (int)
     * created_at, updated_at

6) job_positions_skills
   - Propósito: Unión puesto -> pool de preguntas (qué skill+nivel usa ese puesto).
   - Campos típicos:
     * id (UUID)
     * job_position_id (FK -> job_positions.id)
     * question_pool_id (FK -> question_pools.id)
     * created_at, updated_at

(7) roles / permissions (opcional si también quieres poblar roles del sistema)
   - roles, permissions, role_has_permissions, model_has_roles

NOTAS IMPORTANTES
------------------------------------------------------------
- Este script NO ejecuta SQL en tu BD. Solo genera scripts.
- Ajusta los nombres de tablas/campos si tu DDL difiere (p. ej. user_id en certifiers).
- Requiere variable de entorno OPENAI_API_KEY.

Referencias:
- Respuestas API (/v1/responses) :contentReference[oaicite:2]{index=2}
- Structured Outputs (JSON Schema / Pydantic) :contentReference[oaicite:3]{index=3}
- Auth Bearer API key :contentReference[oaicite:4]{index=4}

Resumen rápido: tablas a poblar sí o sí
Para que funcione la pantalla “Banco de preguntas”

✅ question_pools
✅ questions
✅ question_pools_certifiers (y/o users con rol certifier)
✅ question_validates (si usarás workflow de aprobación)

Para evaluación por puesto de trabajo

✅ job_positions
✅ job_positions_skills
✅ calls (si usarás convocatorias)

Para “cargo/rol” (roles del sistema)

✅ roles + permissions + role_has_permissions + model_has_roles

"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field, ValidationError

# OpenAI SDK (pip install openai)
from openai import OpenAI

# Rich para interfaz visual con colores (fallback para mensajes)
from rich.console import Console
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box
from rich.live import Live
from rich.spinner import Spinner

# CustomTkinter para GUI moderna
import customtkinter as ctk
from tkinter import messagebox, filedialog
import threading

# Inicializar consola con tema de IA
console = Console()

# Configurar CustomTkinter
ctk.set_appearance_mode("dark")  # Modo oscuro moderno
ctk.set_default_color_theme("blue")  # Tema azul (asociado a IA)

# Soporte para archivo .env (opcional: pip install python-dotenv)
try:
    from dotenv import load_dotenv
    try:
        load_dotenv()  # Carga variables desde .env si existe
    except (UnicodeDecodeError, Exception):
        # Si hay problema de encoding (BOM UTF-8), intentar parseo manual
        if os.path.exists('.env'):
            try:
                with open('.env', 'r', encoding='utf-8-sig') as f:  # utf-8-sig maneja BOM automáticamente
                    content = f.read().strip()
                    for line in content.split('\n'):
                        line = line.strip()
                        if line and '=' in line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
            except Exception:
                pass  # Si falla, simplemente no carga .env
except ImportError:
    pass  # Si no está instalado, simplemente no carga .env


# -----------------------------
# 1) Modelos de entrada mínima
# -----------------------------
@dataclass
class PoolInput:
    technical_skill: str
    level: str  # BAJO / MEDIO / ALTO
    question_quantity: int
    certifiers: List[str]  # nombres o correos (según tu lógica)


@dataclass
class JobInput:
    name: str
    skills: List[str]  # lista de skills a asociar (deben existir en pools)


# -----------------------------
# 2) Esquema ESTRICTO de salida
#    (Structured Output)
# -----------------------------
class SqlTableInserts(BaseModel):
    table: str = Field(..., description="Nombre de tabla destino")
    inserts: List[str] = Field(..., description="Lista de sentencias INSERT para esta tabla")


class SeedResponse(BaseModel):
    dialect: str = Field(..., description="mysql | postgres | sqlserver")
    notes: List[str] = Field(default_factory=list, description="Notas / supuestos")
    tables: List[SqlTableInserts] = Field(..., description="INSERTs por tabla")
    full_sql: str = Field(..., description="SQL consolidado (ordenado por dependencias)")


# -----------------------------
# 3) Helpers de consola visuales con Rich
# -----------------------------
def ask(prompt: str, default: Optional[str] = None) -> str:
    """Solicita entrada de texto con estilo visual"""
    prompt_text = Text(prompt, style="cyan bold")
    if default:
        prompt_text.append(f" [default: {default}]", style="dim italic")
    prompt_text.append(":", style="cyan")
    
    response = Prompt.ask(prompt_text, default=default or "")
    return response.strip()


def ask_int(prompt: str, default: int) -> int:
    """Solicita entrada numérica con estilo visual"""
    prompt_text = Text(prompt, style="magenta bold")
    prompt_text.append(f" [default: {default}]", style="dim italic")
    prompt_text.append(":", style="magenta")
    
    while True:
        try:
            response = IntPrompt.ask(prompt_text, default=default)
            return response
        except ValueError:
            console.print("⚠️  [red bold]Ingresa un número entero válido.[/red bold]")


def ask_list(prompt: str) -> List[str]:
    """Solicita lista separada por comas con estilo visual"""
    prompt_text = Text(prompt, style="blue bold")
    prompt_text.append(" (separa con coma)", style="dim")
    prompt_text.append(":", style="blue")
    
    raw = Prompt.ask(prompt_text)
    return [x.strip() for x in raw.split(",") if x.strip()]


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    """Solicita respuesta sí/no con estilo visual"""
    prompt_text = Text(prompt, style="yellow bold")
    return Confirm.ask(prompt_text, default=default)


# -----------------------------
# 4) Construcción del prompt
# -----------------------------
def build_prompt(
    dialect: str,
    use_uuid: bool,
    pools: List[PoolInput],
    jobs: List[JobInput],
    include_roles: bool,
) -> str:
    # Instrucciones claras: que genere SQL por tabla + SQL consolidado
    # y que respete dependencias (pools -> questions -> certifiers -> validates -> job_positions -> job_positions_skills)
    pools_json = [
        {
            "technical_skill": p.technical_skill,
            "level": p.level,
            "question_quantity": p.question_quantity,
            "certifiers": p.certifiers,
        }
        for p in pools
    ]
    jobs_json = [{"name": j.name, "skills": j.skills} for j in jobs]

    # Determinar tipo de ID según dialecto
    if dialect == "sqlserver":
        id_type = "UNIQUEIDENTIFIER" if use_uuid else "IDENTITY(1,1)"
        id_notes = "Para SQL Server: usa IDENTITY(1,1) para autoincrement, UNIQUEIDENTIFIER para UUID. Opcionalmente puedes usar corchetes [nombre] para identificadores."
    elif dialect == "postgres":
        id_type = "UUID" if use_uuid else "SERIAL"
        id_notes = "Para PostgreSQL: usa SERIAL para autoincrement, UUID para UUIDs."
    else:  # mysql
        id_type = "CHAR(36)" if use_uuid else "AUTO_INCREMENT"
        id_notes = "Para MySQL: usa AUTO_INCREMENT o CHAR(36) para UUIDs."
    
    return f"""
Eres un generador de SEED SQL para una app de reclutamiento.

OBJETIVO:
Con los datos de entrada, genera INSERTs SQL (sin ejecutar) para poblar:
- question_pools
- questions
- question_pools_certifiers (si aplica: user_id opcional; usa nombres como referencia si no hay users)
- question_validates (puede ser inicial: status='pending')
- job_positions
- job_positions_skills
Y opcionalmente (si include_roles=true):
- roles, permissions, role_has_permissions, model_has_roles

REGLAS:
- Dialecto: {dialect}
- IDs: {id_type}
  {id_notes}
  Si es UUID, genera UUIDs consistentes y reutilízalos en FKs.
- Ordena por dependencias (primero catálogos/pools, luego preguntas, etc.)
- Genera mínimos datos pero completos para que la app funcione:
  * Para cada pool, crea N preguntas (N=question_quantity). Opciones tipo ABCD en JSON y una correcta.
  * Para certificadores: crea registros en question_pools_certifiers por cada certifier asignado al pool.
  * Crea question_validates para cada pregunta y certifier (status='pending').
  * Para job_positions: crea puestos indicados y asocia skills mediante job_positions_skills apuntando a pools existentes
    (si un puesto incluye skill que no existe, crea el pool por defecto en nivel MEDIO con 5 preguntas).
- No uses instrucciones DDL (solo INSERTs).
- Devuelve:
  1) tables[] con inserts por tabla
  2) full_sql consolidado

DATOS DE ENTRADA (POOLS):
{json.dumps(pools_json, ensure_ascii=False, indent=2)}

DATOS DE ENTRADA (PUESTOS):
{json.dumps(jobs_json, ensure_ascii=False, indent=2)}

include_roles = {str(include_roles).lower()}
""".strip()


# -----------------------------
# 5) Llamada a OpenAI y guardado
# -----------------------------
def generate_seed_sql(prompt: str, model: str, api_key: Optional[str] = None) -> SeedResponse:
    # Usar API key proporcionada, o del entorno, o lanzar error
    if api_key and api_key.strip():
        client = OpenAI(api_key=api_key.strip())
    else:
        client = OpenAI()  # usa OPENAI_API_KEY del entorno

    # Intentar usar structured outputs con beta.chat.completions.parse()
    # Si no está disponible, usar chat.completions con JSON mode
    schema = SeedResponse.model_json_schema()
    schema_description = json.dumps(schema, indent=2, ensure_ascii=False)
    
    try:
        # Método 1: Intentar usar beta.chat.completions.parse() (si está disponible)
        resp = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": "Devuelve únicamente datos estructurados según el esquema Pydantic proporcionado."},
                {"role": "user", "content": prompt},
            ],
            response_format=SeedResponse,
        )
        return resp.choices[0].message.parsed
    except (AttributeError, TypeError) as e:
        # Si el método no existe, usar método alternativo
        pass
    except Exception as e:
        # Si hay otro error (modelo no disponible, etc.), usar método alternativo
        # Mensajes de consola eliminados para modo GUI
        pass
    
    # Método 2: Usar chat.completions con response_format JSON
    try:
        resp = client.chat.completions.create(
        model=model,
            messages=[
                {
                    "role": "system", 
                    "content": f"""Eres un asistente experto en SQL. Devuelve ÚNICAMENTE un JSON válido según este esquema:
{schema_description}

IMPORTANTE: Responde SOLO con el JSON, sin texto adicional, sin markdown, sin explicaciones."""
                },
            {"role": "user", "content": prompt},
        ],
            response_format={"type": "json_object"},  # JSON mode
            temperature=0.3,  # Menor temperatura para respuestas más deterministas
        )
        json_str = resp.choices[0].message.content
        if json_str:
            # Limpiar posibles markdown code blocks o texto adicional
            json_str = json_str.strip()
            # Remover markdown code blocks si existen
            if json_str.startswith("```json"):
                json_str = "\n".join(json_str.split("\n")[1:-1])
            elif json_str.startswith("```"):
                json_str = "\n".join(json_str.split("\n")[1:-1])
            # Intentar encontrar JSON válido si hay texto alrededor
            if "{" in json_str and "}" in json_str:
                start = json_str.find("{")
                end = json_str.rfind("}") + 1
                json_str = json_str[start:end]
            
            return SeedResponse.model_validate_json(json_str)
        else:
            raise ValueError("La respuesta de OpenAI está vacía")
    except Exception as e:
        # Si falla todo, mostrar error útil con rich
        error_msg = str(e)
        if "model_not_found" in error_msg or "404" in error_msg:
            error_panel = Panel(
                f"[bold red]❌ Error: El modelo '{model}' no está disponible o no tienes acceso[/bold red]\n\n"
                "[yellow]Modelos comunes:[/yellow]\n"
                "• gpt-4o-mini\n"
                "• gpt-4o\n"
                "• gpt-4-turbo\n"
                "• gpt-3.5-turbo\n\n"
                "[dim]Verifica que escribiste correctamente el nombre del modelo (debe empezar con 'gpt-')[/dim]",
                border_style="red",
                box=box.ROUNDED
            )
            console.print()
            console.print(error_panel)
        raise


def write_outputs(seed: SeedResponse, out_prefix: str = "seed_output") -> None:
    # JSON
    json_path = f"{out_prefix}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(seed.model_dump_json(indent=2, exclude_none=True))

    # SQL consolidado
    sql_path = f"{out_prefix}.sql"
    with open(sql_path, "w", encoding="utf-8") as f:
        f.write("-- SQL Consolidado\n")
        f.write(seed.full_sql.strip() + "\n")

    # SQL por tabla
    for t in seed.tables:
        safe_name = t.table.replace(".", "_")
        t_path = f"{out_prefix}__{safe_name}.sql"
        with open(t_path, "w", encoding="utf-8") as f:
            f.write(f"-- Inserts para {t.table}\n")
            f.write("\n".join(t.inserts).strip() + "\n")

    # Mostrar resumen visual
    table = Table(title="📁 Archivos Generados", box=box.ROUNDED, border_style="green")
    table.add_column("Tipo", style="cyan", no_wrap=True)
    table.add_column("Archivo", style="white")
    
    table.add_row("📄 JSON", json_path)
    table.add_row("🗃️  SQL Consolidado", sql_path)
    for t in seed.tables:
        safe_name = t.table.replace(".", "_")
        t_path = f"{out_prefix}__{safe_name}.sql"
        table.add_row("📋 SQL Tabla", t_path)
    
    # Solo mostrar en consola si no estamos en GUI
    try:
        console.print()
        console.print(table)
        console.print(f"\n✅ [green bold]Generación completada exitosamente![/green bold]")
    except:
        pass  # Si no hay consola disponible (modo GUI), no hacer nada


def main_gui() -> None:
    """Interfaz gráfica moderna con formularios"""
    
    # Paleta de colores DARK MODE - Verde Matrix Neón
    COLORS = {
        # Fondos oscuros (modo dark puro - Matrix style)
        "bg_dark": "#000000",           # Negro puro - Fondo principal totalmente negro
        "bg_medium": "#000000",         # Negro puro - Frames y secciones
        "bg_light": "#152015",          # Verde oscuro - Elementos internos
        "bg_lighter": "#1a2a1a",        # Verde medio oscuro - Hover states
        
        # Azules reemplazados por Verde Matrix
        "blue_corporate": "#00cc66",    # Verde Matrix medio - Para combos y elementos
        "blue_primary": "#00ff88",      # Verde Matrix neón - Principal (el clásico)
        "blue_secondary": "#00ff99",    # Verde Matrix claro - Secundario
        "blue_light": "#33ffaa",        # Verde Matrix muy claro - Claros
        "blue_hover": "#00dd77",        # Verde Matrix hover - Hover states
        
        # Cyan reemplazado por Verde Matrix
        "cyan_accent": "#00ff88",       # Verde Matrix neón - Acentos
        "cyan_light": "#00ff99",        # Verde Matrix claro - Acentos claros
        
        # Verde Matrix (principales)
        "green_neon": "#00ff88",        # Verde Matrix neón clásico - Principal
        "green_matrix": "#00ff88",      # Verde Matrix neón - Acentos especiales
        "green_dark": "#00cc66",        # Verde Matrix oscuro - Variantes
        
        # Textos y bordes en verde matrix (más suaves)
        "gray_text": "#00ff88",         # Verde Matrix para texto principal
        "gray_secondary": "#00cc66",    # Verde Matrix más oscuro para texto secundario
        "gray_border": "#00ff88",       # Verde Matrix para bordes
    }
    
    # Configurar tema de CustomTkinter - Modo dark puro
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")  # Tema dark-blue para mejor contraste
    
    # Crear ventana principal - Optimizada para una sola pantalla
    app = ctk.CTk()
    app.title("🤖 Generar Scripts SQL")
    
    # Calcular tamaño y posición para centrar perfectamente
    screen_width = app.winfo_screenwidth()
    screen_height = app.winfo_screenheight()
    window_width = int(screen_width * 0.85)  # 85% del ancho de pantalla
    window_height = int(screen_height * 0.85)  # 85% del alto de pantalla
    
    # Centrar ventana
    x = (screen_width // 2) - (window_width // 2)
    y = (screen_height // 2) - (window_height // 2)
    
    app.geometry(f"{window_width}x{window_height}+{x}+{y}")
    app.configure(fg_color=COLORS["bg_dark"])
    app.resizable(True, True)
    
    # Variables para almacenar datos (inicializadas vacías)
    # API key debe iniciar en blanco
    config_data = {
        "api_key": ctk.StringVar(value=""),  # Inicia en blanco
        "dialect": ctk.StringVar(value="mysql"),
        "use_uuid": ctk.BooleanVar(value=True),
        "include_roles": ctk.BooleanVar(value=False),
        "model": ctk.StringVar(value="gpt-4o-mini"),
    }
    
    pools_data: List[Dict] = []
    jobs_data: List[Dict] = []
    
    # Frame principal con scroll - SIN contenedor extra para mejor control
    main_frame = ctk.CTkScrollableFrame(app, fg_color=COLORS["bg_dark"])
    main_frame.pack(fill="both", expand=True, padx=0, pady=0)
    
    # Contenedor interno para centrar todo el contenido - Con borde verde Matrix alrededor de todo el formulario
    content_container = ctk.CTkFrame(main_frame, fg_color=COLORS["bg_dark"], border_width=2, border_color=COLORS["green_matrix"])
    content_container.pack(fill="both", expand=True, padx=20, pady=20)
    
    # Centrar horizontalmente el contenido - Menos padding arriba
    center_wrapper = ctk.CTkFrame(content_container, fg_color="transparent")
    center_wrapper.pack(expand=True, fill="x", padx=10, pady=10)
    
    # Asegurar que el scroll comience desde arriba
    def scroll_to_top():
        try:
            main_frame._parent_canvas.yview_moveto(0)
        except:
            pass
    
    # Ejecutar después de que la ventana esté completamente renderizada
    app.after(150, scroll_to_top)
    
    # Frame para centrar título - Ultra compacto - Menos espacio arriba
    title_container = ctk.CTkFrame(center_wrapper, fg_color="transparent")
    title_container.pack(fill="x", pady=(0, 4))
    
    # Título principal - Verde neón moderno - Centrado (tamaño reducido) - Menos espacio
    title_label = ctk.CTkLabel(
        title_container,
        text="🤖 Generar Scripts SQL",
        font=ctk.CTkFont(size=19, weight="bold"),
        text_color=COLORS["green_neon"]
    )
    title_label.pack(pady=(0, 4))
    
    # === SECCIÓN CONFIGURACIÓN ===
    config_frame = ctk.CTkFrame(center_wrapper, fg_color=COLORS["bg_medium"], border_width=0)
    config_frame.pack(fill="x", pady=(0, 5))
    
    config_title = ctk.CTkLabel(
        config_frame,
        text="⚙️  CONFIGURACIÓN",
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color=COLORS["green_matrix"]
    )
    config_title.pack(pady=(6, 4))
    
    # Fila de configuración en grid para compactar
    config_grid = ctk.CTkFrame(config_frame, fg_color="transparent")
    config_grid.pack(fill="x", padx=10, pady=3)
    
    # API Key - Primera fila, ancho completo
    ctk.CTkLabel(config_grid, text="🔑 API Key (OpenAI):", font=ctk.CTkFont(size=10), text_color=COLORS["green_matrix"]).grid(row=0, column=0, padx=5, pady=2, sticky="w")
    api_key_entry = ctk.CTkEntry(config_grid, textvariable=config_data["api_key"], width=600, height=26,
                                  fg_color=COLORS["bg_light"], border_color=COLORS["gray_border"],
                                  text_color=COLORS["green_matrix"], show="*")  # show="*" para ocultar la clave
    api_key_entry.grid(row=0, column=1, columnspan=3, padx=5, pady=2, sticky="ew")
    
    # Dialecto SQL - Ultra compacto
    ctk.CTkLabel(config_grid, text="Dialecto SQL:", font=ctk.CTkFont(size=10), text_color=COLORS["green_matrix"]).grid(row=1, column=0, padx=5, pady=2, sticky="w")
    dialect_combo = ctk.CTkComboBox(config_grid, values=["mysql", "postgres", "sqlserver"], variable=config_data["dialect"], 
                                    width=140, height=26, fg_color=COLORS["blue_corporate"], button_color=COLORS["blue_primary"],
                                    button_hover_color=COLORS["blue_hover"], text_color=COLORS["bg_dark"], dropdown_fg_color=COLORS["bg_medium"],
                                    dropdown_hover_color=COLORS["bg_lighter"], dropdown_text_color=COLORS["green_matrix"],
                                    state="readonly")
    dialect_combo.grid(row=1, column=1, padx=5, pady=2, sticky="w")
    
    # Modelo - COMBO en lugar de Entry - Ultra compacto
    ctk.CTkLabel(config_grid, text="Modelo:", font=ctk.CTkFont(size=10), text_color=COLORS["green_matrix"]).grid(row=1, column=2, padx=5, pady=2, sticky="w")
    model_combo = ctk.CTkComboBox(
        config_grid, 
        values=["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"],
        variable=config_data["model"],
        width=180,
        height=26,
        fg_color=COLORS["blue_corporate"],
        button_color=COLORS["blue_primary"],
        button_hover_color=COLORS["blue_hover"],
        text_color=COLORS["bg_dark"],
        dropdown_fg_color=COLORS["bg_medium"],
        dropdown_hover_color=COLORS["bg_lighter"],
        dropdown_text_color=COLORS["green_matrix"],
        state="readonly"
    )
    model_combo.grid(row=1, column=3, padx=5, pady=2, sticky="w")
    
    # UUID y Roles en segunda fila - Ultra compacto
    uuid_check = ctk.CTkCheckBox(
        config_grid,
        text="Usar IDs tipo UUID",
        variable=config_data["use_uuid"],
        font=ctk.CTkFont(size=10),
        text_color=COLORS["green_matrix"],
        fg_color=COLORS["blue_primary"],
        hover_color=COLORS["blue_secondary"],
        checkmark_color=COLORS["bg_dark"]
    )
    uuid_check.grid(row=2, column=0, columnspan=2, padx=5, pady=2, sticky="w")
    
    roles_check = ctk.CTkCheckBox(
        config_grid,
        text="También poblar roles/permisos",
        variable=config_data["include_roles"],
        font=ctk.CTkFont(size=10),
        text_color=COLORS["green_matrix"],
        fg_color=COLORS["blue_primary"],
        hover_color=COLORS["blue_secondary"],
        checkmark_color=COLORS["bg_dark"]
    )
    roles_check.grid(row=2, column=2, columnspan=2, padx=5, pady=2, sticky="w")
    
    # === SECCIÓN JOBS (PRIMERO) ===
    jobs_section = ctk.CTkFrame(center_wrapper, fg_color=COLORS["bg_medium"], border_width=0)
    jobs_section.pack(fill="x", pady=(0, 5))
    
    jobs_title = ctk.CTkLabel(
        jobs_section,
        text="💼 PUESTOS DE TRABAJO (Job Positions)",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=COLORS["green_matrix"]
    )
    jobs_title.pack(pady=(6, 3))
    
    jobs_container = ctk.CTkScrollableFrame(jobs_section, height=90, fg_color=COLORS["bg_light"])
    jobs_container.pack(fill="both", expand=True, padx=8, pady=3)
    
    def add_job():
        job_frame = ctk.CTkFrame(jobs_container, fg_color=COLORS["bg_medium"], border_width=1, border_color=COLORS["green_matrix"])
        job_frame.pack(fill="x", pady=5, padx=6)
        
        job_num = len(jobs_data) + 1
        job_info = {
            "name": ctk.StringVar(value=""),
            "skills": ctk.StringVar(value=""),
            "frame": job_frame
        }
        jobs_data.append(job_info)
        
        # Job número - Verde neón moderno - Ultra compacto
        ctk.CTkLabel(job_frame, text=f"Puesto #{job_num}", 
                    font=ctk.CTkFont(size=12, weight="bold"), 
                    text_color=COLORS["green_neon"]).pack(anchor="w", padx=6, pady=(4, 3))
        
        # Grid compacto
        job_grid = ctk.CTkFrame(job_frame, fg_color="transparent")
        job_grid.pack(fill="x", padx=6, pady=2)
        
        # Nombre del puesto - Ultra compacto
        ctk.CTkLabel(job_grid, text="Nombre del Puesto:", width=150, 
                    text_color=COLORS["green_matrix"], font=ctk.CTkFont(size=10)).grid(row=0, column=0, padx=3, pady=2, sticky="w")
        entry_name = ctk.CTkEntry(job_grid, textvariable=job_info["name"], width=260, height=26,
                                 fg_color=COLORS["bg_light"], border_color=COLORS["gray_border"],
                                 text_color=COLORS["green_matrix"])
        entry_name.grid(row=0, column=1, padx=3, pady=2)
        
        # Skills - Ultra compacto
        ctk.CTkLabel(job_grid, text="Skills (separar con coma):", width=150, 
                    text_color=COLORS["green_matrix"], font=ctk.CTkFont(size=10)).grid(row=0, column=2, padx=3, pady=2, sticky="w")
        entry_skills = ctk.CTkEntry(job_grid, textvariable=job_info["skills"], width=260, height=26,
                                   fg_color=COLORS["bg_light"], border_color=COLORS["gray_border"],
                                   text_color=COLORS["green_matrix"])
        entry_skills.grid(row=0, column=3, padx=3, pady=2)
        
        # Botón eliminar - Ultra compacto
        remove_btn = ctk.CTkButton(job_frame, text="❌ Eliminar", 
                                  command=lambda: remove_job(job_info), 
                                  fg_color=COLORS["bg_lighter"],  # Verde Matrix oscuro
                                  hover_color=COLORS["green_matrix"], 
                                  width=80, height=26, text_color=COLORS["green_matrix"],
                                  font=ctk.CTkFont(size=9),
                                  border_width=1,
                                  border_color=COLORS["green_matrix"])
        remove_btn.pack(pady=3)
        
        # Actualizar estado de pools cuando se agrega un job
        update_pools_section_state()
    
    def remove_job(job_info):
        if job_info["frame"] in jobs_container.winfo_children():
            job_info["frame"].destroy()
            jobs_data.remove(job_info)
        
        # Actualizar estado de pools cuando se elimina un job
        update_pools_section_state()
    
    add_job_btn = ctk.CTkButton(jobs_section, text="➕ Agregar Puesto", command=add_job, 
                               fg_color=COLORS["blue_primary"], hover_color=COLORS["blue_secondary"],
                               text_color=COLORS["bg_dark"], font=ctk.CTkFont(size=10, weight="bold"),
                               height=26)
    add_job_btn.pack(pady=3)
    
    # === SECCIÓN POOLS (DESPUÉS DE JOBS) ===
    pools_section = ctk.CTkFrame(center_wrapper, fg_color=COLORS["bg_medium"], border_width=0)
    pools_section.pack(fill="x", pady=(0, 5))
    
    pools_title = ctk.CTkLabel(
        pools_section,
        text="📚 BANCOS DE PREGUNTAS (Question Pools)",
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color=COLORS["green_matrix"]
    )
    pools_title.pack(pady=(6, 3))
    
    # Mensaje de advertencia cuando no hay puestos
    pools_warning = ctk.CTkLabel(
        pools_section,
        text="⚠️ Primero debes agregar al menos un puesto de trabajo para habilitar esta sección",
        font=ctk.CTkFont(size=10),
        text_color=COLORS["green_matrix"],
        wraplength=600
    )
    pools_warning.pack(pady=8, padx=10)
    
    pools_container = ctk.CTkScrollableFrame(pools_section, height=110, fg_color=COLORS["bg_light"])
    # Inicialmente oculto, se mostrará cuando haya jobs
    pools_container.pack_forget()
    
    # Variable para el botón de agregar pool (se definirá después)
    add_pool_btn = None
    
    # Función para actualizar el estado de la sección de pools
    def update_pools_section_state():
        """Habilita o deshabilita la sección de pools según haya puestos ingresados"""
        has_jobs = len(jobs_data) > 0
        
        if has_jobs:
            # Habilitar sección de pools
            pools_warning.pack_forget()  # Ocultar advertencia
            if pools_container not in pools_section.winfo_children() or not pools_container.winfo_ismapped():
                pools_container.pack(fill="both", expand=True, padx=8, pady=3)
            if add_pool_btn:
                add_pool_btn.configure(state="normal", fg_color=COLORS["blue_primary"], text_color=COLORS["bg_dark"])
        else:
            # Deshabilitar sección de pools
            pools_warning.pack(pady=8, padx=10)  # Mostrar advertencia
            pools_container.pack_forget()  # Ocultar contenedor
            # Limpiar pools existentes si no hay jobs
            for pool_info in pools_data[:]:
                if pool_info["frame"] in pools_container.winfo_children():
                    pool_info["frame"].destroy()
            pools_data.clear()
            if add_pool_btn:
                add_pool_btn.configure(state="disabled", fg_color=COLORS["bg_lighter"], text_color=COLORS["green_matrix"])
    
    def add_pool():
        pool_frame = ctk.CTkFrame(pools_container, fg_color=COLORS["bg_medium"], border_width=1, border_color=COLORS["green_matrix"])
        pool_frame.pack(fill="x", pady=5, padx=6)
        
        pool_num = len(pools_data) + 1
        pool_info = {
            "skill": ctk.StringVar(value=""),
            "level": ctk.StringVar(value="BAJO"),
            "quantity": ctk.IntVar(value=5),
            "certifiers": ctk.StringVar(value=""),
            "frame": pool_frame
        }
        pools_data.append(pool_info)
        
        # Pool número - Verde neón moderno - Ultra compacto
        ctk.CTkLabel(pool_frame, text=f"Pool #{pool_num}", 
                    font=ctk.CTkFont(size=12, weight="bold"), 
                    text_color=COLORS["green_neon"]).pack(anchor="w", padx=6, pady=(4, 3))
        
        # Grid compacto para campos
        pool_grid = ctk.CTkFrame(pool_frame, fg_color="transparent")
        pool_grid.pack(fill="x", padx=6, pady=2)
        
        # Habilidad técnica - Ultra compacto
        ctk.CTkLabel(pool_grid, text="Habilidad Técnica:", width=120, 
                    text_color=COLORS["green_matrix"], font=ctk.CTkFont(size=10)).grid(row=0, column=0, padx=3, pady=2, sticky="w")
        entry_skill = ctk.CTkEntry(pool_grid, textvariable=pool_info["skill"], width=200, height=26,
                                   fg_color=COLORS["bg_light"], border_color=COLORS["gray_border"],
                                   text_color=COLORS["green_matrix"])
        entry_skill.grid(row=0, column=1, padx=3, pady=2)
        
        # Nivel - Ultra compacto
        ctk.CTkLabel(pool_grid, text="Nivel:", width=120, 
                    text_color=COLORS["green_matrix"], font=ctk.CTkFont(size=10)).grid(row=0, column=2, padx=3, pady=2, sticky="w")
        level_combo = ctk.CTkComboBox(pool_grid, values=["BAJO", "MEDIO", "ALTO"], 
                                     variable=pool_info["level"], width=120, height=26,
                                     fg_color=COLORS["blue_corporate"], button_color=COLORS["blue_primary"],
                                     button_hover_color=COLORS["blue_hover"], text_color=COLORS["bg_dark"],
                                     dropdown_fg_color=COLORS["bg_medium"], dropdown_hover_color=COLORS["bg_lighter"],
                                     dropdown_text_color=COLORS["green_matrix"],
                                     state="readonly")
        level_combo.grid(row=0, column=3, padx=3, pady=2)
        
        # Cantidad de preguntas - Ultra compacto
        ctk.CTkLabel(pool_grid, text="Cantidad Preguntas:", width=120, 
                    text_color=COLORS["green_matrix"], font=ctk.CTkFont(size=10)).grid(row=1, column=0, padx=3, pady=2, sticky="w")
        entry_qty = ctk.CTkEntry(pool_grid, textvariable=pool_info["quantity"], width=80, height=26,
                                fg_color=COLORS["bg_light"], border_color=COLORS["gray_border"],
                                text_color=COLORS["green_matrix"])
        entry_qty.grid(row=1, column=1, padx=3, pady=2)
        
        # Certificadores - Ultra compacto
        ctk.CTkLabel(pool_grid, text="Certificadores (coma):", width=120, 
                    text_color=COLORS["green_matrix"], font=ctk.CTkFont(size=10)).grid(row=1, column=2, padx=3, pady=2, sticky="w")
        entry_cert = ctk.CTkEntry(pool_grid, textvariable=pool_info["certifiers"], width=200, height=26,
                                 fg_color=COLORS["bg_light"], border_color=COLORS["gray_border"],
                                 text_color=COLORS["green_matrix"])
        entry_cert.grid(row=1, column=3, padx=3, pady=2)
        
        # Botón eliminar - Ultra compacto
        remove_btn = ctk.CTkButton(pool_frame, text="❌ Eliminar", 
                                  command=lambda: remove_pool(pool_info), 
                                  fg_color=COLORS["bg_lighter"],  # Verde Matrix oscuro
                                  hover_color=COLORS["green_matrix"], 
                                  width=80, height=26, text_color=COLORS["green_matrix"],
                                  font=ctk.CTkFont(size=9),
                                  border_width=1,
                                  border_color=COLORS["green_matrix"])
        remove_btn.pack(pady=3)
    
    def remove_pool(pool_info):
        if pool_info["frame"] in pools_container.winfo_children():
            pool_info["frame"].destroy()
            pools_data.remove(pool_info)
    
    # Crear botón de agregar pool (debe crearse después de definir las funciones)
    add_pool_btn = ctk.CTkButton(pools_section, text="➕ Agregar Pool", command=add_pool, 
                                fg_color=COLORS["bg_lighter"], hover_color=COLORS["blue_secondary"],
                                text_color=COLORS["green_matrix"], font=ctk.CTkFont(size=10, weight="bold"),
                                height=26, state="disabled")
    add_pool_btn.pack(pady=3)
    
    # === LABEL DE PROGRESO (definir antes de las funciones) - Centrado ===
    progress_container = ctk.CTkFrame(center_wrapper, fg_color="transparent")
    progress_container.pack(fill="x", pady=3)
    
    progress_label = ctk.CTkLabel(progress_container, text="", font=ctk.CTkFont(size=9), text_color=COLORS["green_neon"])
    progress_label.pack()
    
    # === FUNCIONES DE ACCIÓN ===
    
    # Función para limpiar todos los datos
    def clear_all():
        # Limpiar pools
        for pool_info in pools_data[:]:
            if pool_info["frame"] in pools_container.winfo_children():
                pool_info["frame"].destroy()
        pools_data.clear()
        
        # Limpiar jobs
        for job_info in jobs_data[:]:
            if job_info["frame"] in jobs_container.winfo_children():
                job_info["frame"].destroy()
        jobs_data.clear()
        
        # Resetear configuración a valores por defecto (API key en blanco)
        config_data["api_key"].set("")  # Limpiar API key
        config_data["dialect"].set("mysql")
        config_data["use_uuid"].set(True)
        config_data["include_roles"].set(False)
        config_data["model"].set("gpt-4o-mini")
        
        # Limpiar mensaje de progreso
        progress_label.configure(text="")
        
        # Actualizar estado de pools (se deshabilitará porque no hay jobs)
        update_pools_section_state()
    
    # Función para generar seeds
    def generate():
        # Validación 1: API Key (obligatoria)
        api_key = config_data["api_key"].get().strip()
        if not api_key:
            # Intentar desde entorno como fallback
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                progress_label.configure(text="❌ Error: Debes ingresar una API Key", text_color="#FF6B6B")
                messagebox.showerror("Error de Validación", "⚠️ Debes ingresar una API Key de OpenAI en el campo de configuración.")
                return
        
        # Validación 2: Puestos de trabajo
        if not jobs_data:
            progress_label.configure(text="❌ Error: Debes agregar al menos un puesto de trabajo", text_color="#FF6B6B")
            messagebox.showerror("Error de Validación", "⚠️ Debes agregar al menos un puesto de trabajo antes de generar.")
            return
        
        # Validación 3: Bancos de preguntas
        if not pools_data:
            progress_label.configure(text="❌ Error: Debes agregar al menos un banco de preguntas", text_color="#FF6B6B")
            messagebox.showerror("Error de Validación", "⚠️ Debes agregar al menos un banco de preguntas antes de generar.")
            return
        
        # Validación 4: Verificar que los puestos tengan nombre
        for i, job in enumerate(jobs_data):
            if not job["name"].get().strip():
                progress_label.configure(text=f"❌ Error: El puesto #{i+1} debe tener un nombre", text_color="#FF6B6B")
                messagebox.showerror("Error de Validación", f"⚠️ El puesto #{i+1} debe tener un nombre válido.")
                return
        
        # Validación 5: Verificar que los pools tengan habilidad técnica
        for i, pool in enumerate(pools_data):
            if not pool["skill"].get().strip():
                progress_label.configure(text=f"❌ Error: El pool #{i+1} debe tener una habilidad técnica", text_color="#FF6B6B")
                messagebox.showerror("Error de Validación", f"⚠️ El pool #{i+1} debe tener una habilidad técnica válida.")
                return
            if pool["quantity"].get() <= 0:
                progress_label.configure(text=f"❌ Error: El pool #{i+1} debe tener cantidad de preguntas mayor a 0", text_color="#FF6B6B")
                messagebox.showerror("Error de Validación", f"⚠️ El pool #{i+1} debe tener una cantidad de preguntas mayor a 0.")
                return
        
        # Corregir modelo si es necesario
        model = config_data["model"].get().strip()
        if model.startswith("pgt-"):
            model = model.replace("pgt-", "gpt-", 1)
            config_data["model"].set(model)
        
        # Recolectar datos
        dialect = config_data["dialect"].get().lower()
        if dialect not in ("mysql", "postgres", "sqlserver"):
            dialect = "mysql"
        
        pools = []
        for p in pools_data:
            certs = [c.strip() for c in p["certifiers"].get().split(",") if c.strip()]
            if not certs:
                certs = ["certifier1@example.com"]
            pools.append(PoolInput(
                technical_skill=p["skill"].get(),
                level=p["level"].get(),
                question_quantity=p["quantity"].get(),
                certifiers=certs
            ))
        
        jobs = []
        for j in jobs_data:
            skills = [s.strip() for s in j["skills"].get().split(",") if s.strip()]
            if not skills and pools:
                skills = [pools[0].technical_skill]
            jobs.append(JobInput(name=j["name"].get(), skills=skills))
        
        # Generar en thread separado para no bloquear UI
        def do_generate():
            try:
                progress_label.configure(text="🔄 Generando con IA... Por favor espera...", text_color=COLORS["green_matrix"])
                app.update()
                
                # API key ya validada arriba
                prompt = build_prompt(dialect, config_data["use_uuid"].get(), pools, jobs, config_data["include_roles"].get())
                seed = generate_seed_sql(prompt=prompt, model=model, api_key=api_key)
                
                # Guardar archivos
                out_prefix = filedialog.asksaveasfilename(
                    defaultextension=".sql",
                    initialfile="seed_output",
                    filetypes=[("SQL files", "*.sql"), ("All files", "*.*")]
                )
                
                if out_prefix:
                    # Remover extensión si la tiene
                    out_prefix = out_prefix.rsplit(".", 1)[0]
                    write_outputs(seed, out_prefix=out_prefix)
                    
                    progress_label.configure(text=f"✅ Generación completada! Archivos guardados con prefijo: {out_prefix}", text_color=COLORS["green_neon"])
                    messagebox.showinfo("Éxito", f"¡Archivos generados exitosamente!\n\nPrefijo: {out_prefix}\n\nArchivos creados:\n- {out_prefix}.json\n- {out_prefix}.sql\n- Archivos por tabla")
                else:
                    progress_label.configure(text="⚠️ Generación completada pero no se guardaron archivos", text_color=COLORS["green_matrix"])
                    
            except Exception as e:
                progress_label.configure(text=f"❌ Error: {str(e)}", text_color="#FF6B6B")
                messagebox.showerror("Error", f"Error al generar: {str(e)}")
        
        thread = threading.Thread(target=do_generate, daemon=True)
        thread.start()
    
    # === BOTONES DE ACCIÓN - Centrados ===
    action_frame = ctk.CTkFrame(center_wrapper, fg_color="transparent")
    action_frame.pack(fill="x", pady=(4, 5))
    
    # Contenedor interno para centrar botones
    buttons_container = ctk.CTkFrame(action_frame, fg_color="transparent")
    buttons_container.pack(expand=True)
    
    # Botón Limpiar - Centrado - Ultra compacto
    clear_btn = ctk.CTkButton(
        buttons_container,
        text="🗑️  LIMPIAR DATOS",
        command=clear_all,
        font=ctk.CTkFont(size=11, weight="bold"),
        fg_color=COLORS["bg_lighter"],
        hover_color=COLORS["bg_medium"],
        text_color="#ffffff",  # Texto blanco para mejor contraste
        width=150,
        height=32,
        border_width=1,
        border_color=COLORS["green_matrix"]
    )
    clear_btn.pack(side="left", padx=8)
    
    # Botón Generar - Destacado con verde neón - Centrado - Ultra compacto
    generate_btn = ctk.CTkButton(
        buttons_container,
        text="🚀 Generar Scripts",
        command=generate,
        font=ctk.CTkFont(size=13, weight="bold"),
        fg_color=COLORS["green_neon"],
        hover_color=COLORS["green_matrix"],
        text_color=COLORS["bg_dark"],
        width=240,
        height=32
    )
    generate_btn.pack(side="left", padx=8)
    
    # NO inicializar con datos (iniciar limpio)
    # Los datos se agregan solo cuando el usuario hace click en "Agregar"
    
    # Inicializar estado: pools deshabilitados al inicio (después de crear todo)
    update_pools_section_state()
    
    # Ejecutar aplicación
    app.mainloop()


def main() -> None:
    """Versión CLI (mantenida para compatibilidad)"""
    # Banner de bienvenida visual
    welcome_panel = Panel.fit(
        "[bold cyan]🤖 Generador de Seeds SQL con IA[/bold cyan]\n"
        "[dim]Powered by OpenAI / ChatGPT[/dim]",
        border_style="cyan",
        box=box.DOUBLE,
        padding=(1, 2)
    )
    console.print(welcome_panel)
    console.print()

    # Configuración con paneles visuales
    config_panel = Panel(
        "[bold yellow]⚙️  CONFIGURACIÓN INICIAL[/bold yellow]",
        border_style="yellow",
        box=box.ROUNDED
    )
    console.print(config_panel)
    console.print()

    dialect = ask("Dialecto SQL", "mysql").lower().strip()
    if dialect not in ("mysql", "postgres", "sqlserver"):
        console.print("⚠️  [yellow]Dialecto no reconocido; usaré mysql por defecto.[/yellow]")
        dialect = "mysql"

    use_uuid = ask_yes_no("¿IDs tipo UUID?", True)
    include_roles = ask_yes_no("¿También poblar roles/permisos?", False)
    model = ask("Modelo (recomendado: gpt-4o-mini)", "gpt-4o-mini").strip()
    
    # Validar y corregir errores tipográficos comunes en el nombre del modelo
    if model.startswith("pgt-"):
        console.print(f"⚠️  [yellow]Corrigiendo nombre de modelo: {model} -> {model.replace('pgt-', 'gpt-', 1)}[/yellow]")
        model = model.replace("pgt-", "gpt-", 1)

    console.print()

    # Entrada de Pools con panel visual
    pools_panel = Panel(
        "[bold magenta]📚 BANCOS DE PREGUNTAS (Question Pools)[/bold magenta]",
        border_style="magenta",
        box=box.ROUNDED
    )
    console.print(pools_panel)
    console.print()

    pools: List[PoolInput] = []
    n_pools = ask_int("¿Cuántos bancos (question_pools) deseas crear?", 2)

    for i in range(n_pools):
        console.print()
        pool_sub_panel = Panel(
            f"[bold cyan]Pool #{i+1}[/bold cyan]",
            border_style="cyan",
            box=box.SIMPLE
        )
        console.print(pool_sub_panel)
        skill = ask("Habilidad Técnica (technical_skill)", f"Skill{i+1}")
        level = ask("Nivel (BAJO/MEDIO/ALTO)", "BAJO").upper()
        q_qty = ask_int("Cantidad de preguntas (question_quantity)", 5)
        certs = ask_list("Certificadores (nombres o emails)")
        if not certs:
            certs = ["certifier1@example.com"]
        pools.append(PoolInput(skill, level, q_qty, certs))

    console.print()

    # Entrada de Puestos con panel visual
    jobs_panel = Panel(
        "[bold blue]💼 PUESTOS DE TRABAJO (Job Positions)[/bold blue]",
        border_style="blue",
        box=box.ROUNDED
    )
    console.print(jobs_panel)
    console.print()

    jobs: List[JobInput] = []
    n_jobs = ask_int("¿Cuántos puestos (job_positions) deseas crear?", 1)
    for i in range(n_jobs):
        console.print()
        job_sub_panel = Panel(
            f"[bold cyan]Puesto #{i+1}[/bold cyan]",
            border_style="cyan",
            box=box.SIMPLE
        )
        console.print(job_sub_panel)
        name = ask("Nombre del puesto", f"Puesto{i+1}")
        skills = ask_list("Skills a evaluar (deben coincidir con technical_skill)")
        if not skills:
            skills = [pools[0].technical_skill]
        jobs.append(JobInput(name, skills))

    # Prompt y generación con indicador visual
    console.print()
    generation_panel = Panel(
        "[bold green]🚀 GENERANDO SEEDS SQL CON IA...[/bold green]\n"
        f"[dim]Modelo: {model}[/dim]",
        border_style="green",
        box=box.ROUNDED
    )
    console.print(generation_panel)
    console.print()

    prompt = build_prompt(dialect, use_uuid, pools, jobs, include_roles)

    # Mostrar spinner mientras genera
    with Live(Spinner("dots", text="[cyan]Generando con IA..."), console=console, refresh_per_second=10):
        try:
            seed = generate_seed_sql(prompt=prompt, model=model)
        except ValidationError as ve:
            console.print()
            error_panel = Panel(
                f"[bold red]❌ Error: La respuesta no cumplió el esquema[/bold red]\n\n{str(ve)}",
                border_style="red",
                box=box.ROUNDED
            )
            console.print(error_panel)
            return
        except Exception as e:
            console.print()
            error_panel = Panel(
                f"[bold red]❌ Error inesperado[/bold red]\n\n{str(e)}",
                border_style="red",
                box=box.ROUNDED
            )
            console.print(error_panel)
            raise

    console.print()
    console.print("[green bold]✅ Generación completada![/green bold]")
    console.print()

    # Mostrar notas si existen
    if seed.notes:
        notes_panel = Panel(
            "[bold yellow]📝 Notas del Generador[/bold yellow]\n\n" + "\n".join(f"• {n}" for n in seed.notes),
            border_style="yellow",
            box=box.ROUNDED
        )
        console.print(notes_panel)
        console.print()

    # Guardar outputs
    out_prefix = ask("Prefijo de salida de archivos", "seed_output")
    write_outputs(seed, out_prefix=out_prefix)

    console.print()
    final_panel = Panel.fit(
        "[bold green]✅ ¡Proceso Completado![/bold green]\n\n"
        "[dim]Ejecuta los archivos .sql en tu BD[/dim]\n"
        "[red]⚠️  IMPORTANTE: Prueba primero en un entorno de desarrollo[/red]",
        border_style="green",
        box=box.DOUBLE
    )
    console.print(final_panel)


if __name__ == "__main__":
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # Mostrar error en GUI si es posible, sino en consola
        try:
            import tkinter.messagebox as mb
            root = ctk.CTk()
            root.withdraw()  # Ocultar ventana principal
            error_msg = (
                "❌ Falta OPENAI_API_KEY en variables de entorno\n\n"
                "📝 OPCIONES PARA CONFIGURAR:\n\n"
                "1️⃣  Archivo .env (RECOMENDADO):\n"
                "   • Crea un archivo .env en la raíz del proyecto\n"
                "   • Agrega: OPENAI_API_KEY=sk-tu-api-key-aqui\n"
                "   • Instala: pip install python-dotenv\n\n"
                "2️⃣  Variable de entorno TEMPORAL (PowerShell):\n"
                "   $env:OPENAI_API_KEY = \"sk-tu-api-key-aqui\"\n\n"
                "3️⃣  Variable de entorno PERMANENTE (PowerShell como Admin):\n"
                "   setx OPENAI_API_KEY \"sk-tu-api-key-aqui\"\n"
                "   (Cierra y abre una nueva ventana de PowerShell)\n\n"
                "4️⃣  Linux/Mac:\n"
                "   export OPENAI_API_KEY=\"sk-tu-api-key-aqui\""
            )
            mb.showerror("Error de Configuración", error_msg)
            root.destroy()
        except:
            # Fallback a consola
            error_config_panel = Panel.fit(
                "[bold red]❌ Falta OPENAI_API_KEY en variables de entorno[/bold red]\n\n"
                "[bold yellow]📝 OPCIONES PARA CONFIGURAR:[/bold yellow]\n\n"
                "[cyan]1️⃣  Archivo .env (RECOMENDADO):[/cyan]\n"
                "   • Crea un archivo .env en la raíz del proyecto\n"
                "   • Agrega: OPENAI_API_KEY=sk-tu-api-key-aqui\n"
                "   • Instala: pip install python-dotenv\n\n"
                "[magenta]2️⃣  Variable de entorno TEMPORAL (PowerShell):[/magenta]\n"
                "   $env:OPENAI_API_KEY = \"sk-tu-api-key-aqui\"\n\n"
                "[blue]3️⃣  Variable de entorno PERMANENTE (PowerShell como Admin):[/blue]\n"
                "   setx OPENAI_API_KEY \"sk-tu-api-key-aqui\"\n"
                "   (Cierra y abre una nueva ventana de PowerShell)\n\n"
                "[green]4️⃣  Linux/Mac:[/green]\n"
                "   export OPENAI_API_KEY=\"sk-tu-api-key-aqui\"",
                border_style="red",
                box=box.DOUBLE,
                padding=(1, 2)
            )
            console.print(error_config_panel)
        raise SystemExit(1)

    # Usar GUI moderna por defecto
    main_gui()
