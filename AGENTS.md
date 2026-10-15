# Reglas del proyecto

- La fuente canónica es `~/projects/tinyWidgets`: hacer allí todos los cambios de código y documentación. Aplicarlos al escritorio con `scripts/install.sh`; no editar directamente las copias instaladas en `~/.local/lib` o los módulos de `~/.config/eww`. Los datos personales y las integraciones externas permanecen fuera del repositorio.

- No ejecutar `git push` sin autorización explícita del usuario.
- Usar Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `build:`, `refactor:`.
- No añadir trailers `Co-authored-by`.
- Documentar cambios de comportamiento, requisitos y limitaciones.
- Ejecutar las pruebas correspondientes antes de hacer commit.
- Conservar instancias, perfiles, atajos y archivos personales al instalar.
- No versionar credenciales, cuotas de API, estado, generaciones ni configuración personal.
- Mantener el gestor en Rust y el editor GTK en Python. IN/OUT usan transforms/revealer de Eww, sin animaciones CSS.
