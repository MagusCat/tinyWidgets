# Desarrollo y control de versión

El repositorio de trabajo es `~/projects/tinyWidgets`. El remoto esperado es `https://github.com/MagusCat/tinyWidgets.git`.

## Reglas

- Nunca hacer push sin autorización explícita del propietario.
- Conventional Commits: `feat:`, `fix:`, `refactor:`, `test:`, `build:` o `docs:` y una descripción concreta.
- No añadir `Co-authored-by`.
- Documentar requisitos, comportamiento nuevo y limitaciones.
- No incluir estado ni datos personales.

## Comprobaciones

```sh
./scripts/test.sh
```

Incluye formato, unidades Rust, regresiones Python y pruebas del binario con Eww/Wayfire simulados. El transporte simulado requiere la característica Cargo `test-transport`, sólo para depuración. La compilación de producción no la habilita. Las pruebas de instalación usan directorios temporales.

Después de cambios gráficos, ejecutar también `widgetctl validate --graphics` y revisar el escritorio dentro de una sesión Wayfire. Este paso no se puede sustituir por tests sin compositor.

## Historial remoto pendiente

La preparación inicial local se realizó sin conexión DNS a GitHub. La rama local no afirma representar el historial remoto. Antes de integrar o publicar:

```sh
git fetch origin
git log --oneline --graph --all
```

Revisar la rama predeterminada remota e integrar el trabajo mediante cherry-pick o una rama basada en ella. No usar force push ni sobrescribir historia remota. Obtener autorización antes de cualquier push.
