from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime
import os

app = FastAPI(title="AI Service")

suggestions_history = []
circuit_breaker = {"failures": 0, "open": False}

class CodeAnalysis(BaseModel):
    session_id: str
    user: str
    code: str
    language: str = "python"
    question: Optional[str] = None

def analyze_code_locally(code: str, language: str, question: Optional[str]) -> str:
    lines = code.strip().split('\n')
    total_lines = len(lines)
    suggestions = []
    warnings = []
    good = []

    if not code.strip():
        return "El código está vacío. Por favor escribe algo para analizar."

    if language == "python":
        has_functions = "def " in code
        has_classes = "class " in code
        has_imports = any(l.strip().startswith("import") or l.strip().startswith("from") for l in lines)
        has_docstring = '"""' in code or "'''" in code
        has_type_hints = "->" in code or ": int" in code or ": str" in code or ": list" in code or ": dict" in code or ": float" in code or ": bool" in code
        has_return = "return " in code
        has_try_except = "try:" in code
        has_bare_except = "except:" in code
        has_print = "print(" in code
        has_main = 'if __name__' in code
        has_comments = any(l.strip().startswith("#") for l in lines)
        has_list_comp = "[" in code and "for" in code and "in" in code
        has_enumerate = "enumerate(" in code
        has_range_len = "range(len(" in code
        indentation_ok = all(
            l == '' or l.startswith(' ') or l.startswith('\t') or not l[0].isspace() or l.startswith('def') or l.startswith('class') or l.startswith('import') or l.startswith('from') or l.startswith('#')
            for l in lines
        )

        if has_functions:
            good.append("✅ Buena estructura: funciones bien definidas con `def`.")
        if has_classes:
            good.append("✅ Excelente uso de programación orientada a objetos con clases.")
        if has_imports:
            good.append("✅ Importaciones organizadas correctamente al inicio del archivo.")
        if has_docstring:
            good.append("✅ Documentación con docstrings presente — muy buena práctica.")
        if has_type_hints:
            good.append("✅ Type hints detectados — el código es más legible y mantenible.")
        if has_return and has_functions:
            good.append("✅ Las funciones retornan valores correctamente.")
        if has_try_except and not has_bare_except:
            good.append("✅ Manejo de excepciones específico — excelente práctica.")
        if has_main:
            good.append("✅ Uso correcto de `if __name__ == '__main__'` — estructura profesional.")
        if has_comments:
            good.append("✅ Código comentado — facilita la comprensión y el mantenimiento.")
        if has_list_comp:
            good.append("✅ List comprehensions detectadas — código pythónico y eficiente.")
        if has_enumerate:
            good.append("✅ Uso de `enumerate()` — forma correcta de iterar con índices.")
        if total_lines <= 30:
            good.append("✅ Longitud de código adecuada — conciso y bien estructurado.")

        if has_bare_except:
            warnings.append("⚠️ Evita `except:` sin especificar el tipo — usa `except ValueError:` o similar.")
        if has_range_len:
            warnings.append("⚠️ Reemplaza `range(len(lista))` por `enumerate(lista)` — más pythónico.")
        if not has_docstring and has_functions:
            warnings.append("💡 Agrega docstrings a tus funciones: explica qué hacen, parámetros y retorno.")
        if not has_type_hints and has_functions:
            warnings.append("💡 Considera agregar type hints: `def suma(a: int, b: int) -> int:`")
        if total_lines > 50:
            warnings.append("💡 El archivo es largo — considera dividirlo en módulos separados.")

        if question:
            q = question.lower()
            if "optimiz" in q or "mejor" in q or "eficien" in q:
                suggestions.append("💬 Para optimizar: usa list comprehensions, evita loops anidados innecesarios y prefiere estructuras de datos eficientes como sets para búsquedas.")
            elif "error" in q or "falla" in q or "excepcion" in q:
                suggestions.append("💬 Para manejo de errores: usa bloques try/except específicos, loggea los errores y nunca uses `except:` sin tipo.")
            elif "legib" in q or "limpi" in q or "clean" in q:
                suggestions.append("💬 Para mejor legibilidad: sigue PEP 8, usa nombres descriptivos, agrega docstrings y mantén funciones cortas (máx 20 líneas).")
            elif "segur" in q:
                suggestions.append("💬 Para seguridad: nunca expongas credenciales en el código, valida todas las entradas y usa variables de entorno para datos sensibles.")
            elif "prueba" in q or "test" in q:
                suggestions.append("💬 Para testing: usa `unittest` o `pytest`, escribe pruebas para cada función y apunta a más del 80% de cobertura.")
            else:
                suggestions.append(f"💬 Sobre tu pregunta '{question}': revisa la documentación oficial de Python en docs.python.org para más detalles.")

    all_feedback = good + warnings + suggestions

    if not all_feedback:
        all_feedback.append("✅ El código tiene una estructura correcta. Continúa con buenas prácticas.")

    summary = f"📊 Análisis completado — {total_lines} líneas analizadas. "
    if len(good) > 0:
        summary += f"{len(good)} aspectos positivos encontrados."

    return summary + " | " + " | ".join(all_feedback)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "ai-service",
        "circuit_breaker": "open" if circuit_breaker["open"] else "closed",
        "ai_provider": "local-analyzer"
    }

@app.post("/ai/analyze")
def analyze_code(request: CodeAnalysis):
    if circuit_breaker["open"]:
        suggestion_text = "⚠️ Asistente de IA temporalmente no disponible. " + analyze_code_locally(request.code, request.language, request.question)
    else:
        try:
            suggestion_text = analyze_code_locally(request.code, request.language, request.question)
            circuit_breaker["failures"] = 0
        except Exception as e:
            circuit_breaker["failures"] += 1
            if circuit_breaker["failures"] >= 3:
                circuit_breaker["open"] = True
            suggestion_text = "⚠️ Error en el análisis. Intenta de nuevo."

    result = {
        "suggestion_id": str(uuid.uuid4()),
        "session_id": request.session_id,
        "user": request.user,
        "code_received": request.code,
        "suggestion": suggestion_text,
        "language": request.language,
        "timestamp": datetime.now().isoformat(),
        "ai_provider": "local-analyzer"
    }

    suggestions_history.append(result)
    return result

@app.get("/ai/history")
def get_history():
    return {"total": len(suggestions_history), "suggestions": suggestions_history}

@app.get("/ai/history/{session_id}")
def get_history_by_session(session_id: str):
    filtered = [s for s in suggestions_history if s["session_id"] == session_id]
    if not filtered:
        raise HTTPException(status_code=404, detail="No hay sugerencias para esta sesión")
    return {"session_id": session_id, "suggestions": filtered}

@app.post("/ai/circuit-breaker/open")
def open_circuit_breaker():
    circuit_breaker["open"] = True
    circuit_breaker["failures"] = 3
    return {"message": "Circuit breaker abierto — IA simulando fallo", "status": circuit_breaker}

@app.post("/ai/circuit-breaker/close")
def close_circuit_breaker():
    circuit_breaker["open"] = False
    circuit_breaker["failures"] = 0
    return {"message": "Circuit breaker cerrado — IA restaurada", "status": circuit_breaker}