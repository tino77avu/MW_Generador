# 🤖 Generador de Scripts SQL

Aplicación con interfaz gráfica moderna para generar scripts SQL (seeds) usando inteligencia artificial (OpenAI/GPT).

## 🚀 Características

- ✨ Interfaz gráfica moderna con tema dark y colores Matrix
- 🔧 Soporte para múltiples dialectos SQL: MySQL, PostgreSQL, SQL Server
- 🎯 Generación automática de scripts SQL para poblar tablas de bases de datos
- 🔑 Configuración de API Key directamente desde la interfaz
- 📝 Generación de seeds para bancos de preguntas, puestos de trabajo y más

## 📋 Requisitos

- Python 3.8 o superior
- API Key de OpenAI

## 🛠️ Instalación

1. Clona el repositorio:
```bash
git clone <url-del-repositorio>
cd MWinner
```

2. Instala las dependencias:
```bash
pip install -r requirements.txt
```

3. **No se requiere configuración previa**: La API Key de OpenAI se ingresa directamente en la aplicación al ejecutarla.
   
   > **Nota opcional**: Si prefieres, puedes crear un archivo `.env` con `OPENAI_API_KEY=tu-api-key-aqui` como respaldo (la aplicación lo usará como fallback si no se ingresa la clave en el formulario).

## 🎮 Uso

Ejecuta la aplicación:
```bash
python MW_Scripts.py
```

### Flujo de trabajo:

1. **Ingresa tu API Key de OpenAI** en el campo de la sección "Configuración"
2. **Configura los parámetros:**
   - Selecciona el dialecto SQL (MySQL, PostgreSQL, SQL Server)
   - Elige el modelo de OpenAI (gpt-4o-mini, gpt-4o, etc.)
   - Configura si usar UUID o autoincrement
3. **Agrega puestos de trabajo** (obligatorio primero)
4. **Agrega bancos de preguntas** (se habilita después de agregar al menos un puesto)
5. **Genera los scripts SQL** haciendo clic en "🚀 Generar Scripts"

## 📦 Dependencias

- `openai` - Cliente para la API de OpenAI
- `customtkinter` - Interfaz gráfica moderna
- `python-dotenv` - Carga de variables de entorno (opcional, solo como fallback)
- `pydantic` - Validación de datos
- `rich` - Mejoras en la consola (modo CLI)

## 📝 Notas

- Los scripts generados son INSERTs SQL listos para ejecutar
- La aplicación NO ejecuta SQL en tu base de datos, solo genera los scripts
- Asegúrate de revisar los scripts generados antes de ejecutarlos en producción

## 🔒 Seguridad

- **NO** compartas tu API Key públicamente
- La API Key se ingresa directamente en la aplicación y **NO se guarda** en ningún archivo
- **NO** subas archivos `.env` al repositorio si decides usarlos (ya está en .gitignore)
- La aplicación usa la API Key solo durante la ejecución para realizar las llamadas a OpenAI

## 📄 Licencia

Este proyecto es de uso libre.

