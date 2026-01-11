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

3. Configura tu API Key de OpenAI:
   - Opción 1: Ingresa tu API Key directamente en la aplicación
   - Opción 2: Crea un archivo `.env` en la raíz del proyecto:
   ```
   OPENAI_API_KEY=tu-api-key-aqui
   ```

## 🎮 Uso

Ejecuta la aplicación:
```bash
python MW_Scripts.py
```

### Flujo de trabajo:

1. **Ingresa tu API Key** (si no está en el archivo .env)
2. **Configura los parámetros:**
   - Selecciona el dialecto SQL (MySQL, PostgreSQL, SQL Server)
   - Elige el modelo de OpenAI (gpt-4o-mini, gpt-4o, etc.)
   - Configura si usar UUID o autoincrement
3. **Agrega puestos de trabajo** (obligatorio primero)
4. **Agrega bancos de preguntas** (se habilita después de agregar puestos)
5. **Genera los scripts SQL**

## 📦 Dependencias

- `openai` - Cliente para la API de OpenAI
- `customtkinter` - Interfaz gráfica moderna
- `python-dotenv` - Carga de variables de entorno (opcional)
- `pydantic` - Validación de datos
- `rich` - Mejoras en la consola (modo CLI)

## 📝 Notas

- Los scripts generados son INSERTs SQL listos para ejecutar
- La aplicación NO ejecuta SQL en tu base de datos, solo genera los scripts
- Asegúrate de revisar los scripts generados antes de ejecutarlos en producción

## 🔒 Seguridad

- **NO** subas tu archivo `.env` al repositorio (ya está en .gitignore)
- **NO** compartas tu API Key públicamente
- La aplicación permite ingresar la API Key desde la interfaz, pero se recomienda usar el archivo `.env`

## 📄 Licencia

Este proyecto es de uso libre.

