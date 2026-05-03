---
name: implementarFuncionalidad
description: "Diseña un plan para implementar una funcionalidad y lo devuelve para que el usuario lo apruebe antes de ejecutarlo. Los dos últimos pasos del plan son siempre, en este orden, la invocación de @agent-tests-author-from-diff y @agent-guides-updater-from-diff."
argument-hint: ruta a un .md con la descripción de la funcionalidad y/o explicaciones inline (cualquiera de las dos cosas o ambas)
disable-model-invocation: true
---

Quiero que implementes una funcionalidad cuya información puede estar repartida entre la conversación actual, un archivo `.md` que te paso como argumento, y/o explicaciones inline pasadas también como argumento. Cualquiera de esos canales puede contener la descripción — léelos todos.

Es posible que en %ARGUMENTS también te pase alguna indicación sobre cómo hacer los tests o los archivos md si es así deberás pasarselo a los subagentes como task prompt.

Argumento recibido: $ARGUMENTS

Antes de tocar código, sigue este flujo en este orden:

1. Lee la conversación entera, el archivo `.md` (si `$ARGUMENTS` apunta a uno) y todas las explicaciones inline.
2. Investiga el código del proyecto lo necesario para entender el alcance, las capas afectadas y cualquier convención que aplique.
3. Construye un plan detallado paso a paso.
4. Devuélveme el plan y **espera mi aprobación**. No empieces a implementar hasta que lo acepte.

**Estructura obligatoria del plan — los dos últimos pasos son siempre estos, en este orden exacto:**

- **Penúltimo paso — Tests:** ejecutar el subagente `@agent-tests-author-from-diff` 
- **Último paso — Documentación:** ejecutar el subagente `@agent-guides-updater-from-diff` 

**Reglas duras sobre los pasos previos a esos dos — fundamentales y no negociables:**

Todos los pasos anteriores al paso de tests contienen ÚNICAMENTE la implementación del código de la funcionalidad. Hasta llegar al paso de tests:

- NO se crea ni se edita ningún test bajo `backend/tests/`, `frontend/src/test/` o `frontend/e2e/`.
- NO se edita ningún archivo `.md` — ni `*_guide.md`, ni `README.md`, ni ningún otro.

De los tests se encarga exclusivamente el subagente del penúltimo paso. De la documentación se encarga exclusivamente el subagente del último paso. La división es estricta y no se mezcla.

Si al revisar tu propio plan detectas que se cuela un paso de tests o de edición de `.md` antes del penúltimo paso, regenera el plan limpio antes de entregármelo.
