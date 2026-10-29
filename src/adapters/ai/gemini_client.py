import os
from typing import Any

from google import genai
from google.genai import types


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model
        self._client: genai.Client | None = None

        if self.api_key:
            self._client = genai.Client(api_key=self.api_key)

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def generate_qa_fallback(
        self,
        question: str,
        input_type: str,
        candidate_profile_context: str,
    ) -> str:
        if not self._client:
            return "Experiencia demostrable en proyectos reales acorde al perfil."

        prompt = (
            "Eres un copiloto ATS experto para un desarrollador de software Junior/Mid en Colombia. "
            "Responde de forma concisa, directa y profesional la siguiente pregunta de un formulario de postulación.\n\n"
            f"Contexto del candidato:\n{candidate_profile_context}\n\n"
            f"Tipo de input HTML: {input_type}\n"
            f"Pregunta del formulario: {question}\n\n"
            "Reglas estrictas:\n"
            "- Si el input es numérico, responde únicamente el número entero sin puntos ni letras.\n"
            "- Nunca inventes experiencia falsa ni respondas 0 para tecnologías donde el candidato tiene nociones.\n"
            "- Devuelve solo el valor final a colocar en el campo."
        )

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return (response.text or "").strip()

    def tailor_cv(
        self,
        job_title: str,
        job_description: str,
        cv_base_markdown: str,
    ) -> str:
        if not self._client:
            return (
                f"### ATS Gap & Tailoring para {job_title}\n\n"
                "* **Brecha de Keywords:** Revisar requerimientos específicos del stack.\n"
                "* **Bullets Recomendados:** Destacar experiencia práctica con React, Node.js y bases de datos relacionales.\n"
                "* **Nota:** Simulación offline (configura GEMINI_API_KEY para análisis en vivo)."
            )

        clean_desc = job_description[:4000]
        prompt = (
            f"Analiza la siguiente vacante para el rol '{job_title}' y compárala contra la hoja de vida base del candidato en Markdown.\n\n"
            f"Descripción de la vacante (recortada a 4,000 caracteres):\n{clean_desc}\n\n"
            f"Hoja de vida base:\n{cv_base_markdown}\n\n"
            "Estructura tu respuesta exactamente con estas dos secciones en Markdown:\n"
            "### 1. Brecha de Keywords ATS (ATS Gap)\n"
            "Lista de conceptos o tecnologías clave que la oferta exige explícitamente y que no están redactadas de esa forma en el CV base.\n\n"
            "### 2. Bullets Sugeridos de Adaptación (2 a 3 viñetas)\n"
            "Cómo reenfocar los proyectos o experiencia real del candidato para alinearse con esta vacante, sin inventar tecnologías que no maneje."
        )

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return (response.text or "").strip()

    def prepare_interview(
        self,
        job_title: str,
        company: str,
        job_description: str,
        candidate_stack: list[str],
    ) -> str:
        if not self._client:
            stack_str = ", ".join(candidate_stack)
            return (
                f"# Guía de Preparación Técnica — {job_title} en {company}\n\n"
                f"## 1. Resumen del Rol\nRol técnico enfocado en {stack_str}.\n\n"
                "## 2. 5 Preguntas Técnicas Clave\n1. Manejo de estado y ciclo de vida en React.\n"
                "2. Arquitectura de servicios y manejo de dependencias en NestJS/Node.js.\n"
                "3. Optimización de consultas e índices en PostgreSQL.\n"
                "4. Manejo de promesas y asincronía en TypeScript.\n"
                "5. Principios de arquitectura limpia y testing.\n\n"
                "## 3. Reto de Live Coding\nImplementar un servicio REST con validación de entradas.\n\n"
                "## 4. Preguntas para el Entrevistador\n1. ¿Cuál es la arquitectura actual del backend?\n"
                "2. ¿Cómo es el flujo de despliegue y code review?\n"
                "3. ¿Cuáles son los mayores retos técnicos del equipo este trimestre?\n"
            )

        clean_desc = job_description[:4000]
        prompt = (
            f"Genera una guía técnica completa de preparación de entrevista para el candidato.\n"
            f"Empresa: {company}\n"
            f"Cargo: {job_title}\n"
            f"Stack del candidato: {', '.join(candidate_stack)}\n\n"
            f"Descripción de la oferta:\n{clean_desc}\n\n"
            "Genera un documento Markdown con las siguientes 4 secciones:\n"
            "# Guía de Preparación Técnica — [Cargo] en [Empresa]\n"
            "## 1. Resumen del Rol y Mapa de Temas Críticos\n"
            "## 2. 5 Preguntas Técnicas Nivel Junior/Mid con Respuestas Guía\n"
            "## 3. Reto Práctico de Live Coding (Enunciado + Solución en TypeScript)\n"
            "## 4. 3 Preguntas Inteligentes para Hacerle al Entrevistador\n"
        )

        response = self._client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return (response.text or "").strip()
