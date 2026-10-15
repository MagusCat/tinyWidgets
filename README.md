# tinyWidgets

Widgets de escritorio modulares para Wayfire y Eww. Gestor en **Rust**, editor visual y proveedores en **Python/GTK3**. Cada widget tiene su manifiesto, vista, estilo y proveedor; cada instancia conserva posición, opciones y workspace independientes.

Estado: migración a Rust implementada y cubierta por pruebas automatizadas. La validación visual del nuevo gestor en una sesión Wayfire sigue pendiente. No hay cifras de FPS o consumo verificadas.

## Requisitos

| Área | Dependencias |
| --- | --- |
| Escritorio | Linux, sesión Wayland con Wayfire, IPC habilitado y `WAYFIRE_SOCKET` disponible |
| Renderizado | Eww con soporte Wayland, transforms y revealer; GTK3 y gtk-layer-shell |
| Compilación | Rust estable, Cargo, compilador/enlazador del sistema, `pkg-config`, bibliotecas de desarrollo GTK3 |
| Editor | Python 3.10 o posterior, PyGObject (`gi`), Pycairo, introspección GTK3, Gdk, Pango y GtkLayerShell |
| Utilidades | `sha256sum`; fuente Nerd Font para los iconos |
| Opcionales | Matugen para colores del fondo; herramientas específicas indicadas en cada `manifest.json` |

Entorno de compilación actual: Rust 1.99.0, Python 3.14.8 y GTK 3.24.52. Eww usado por los dotfiles: 0.5.0. Estas son las versiones comprobadas localmente; todavía no hay una matriz de compatibilidad.

Los scripts no instalan paquetes del sistema ni requieren `sudo`. Instala las dependencias con el gestor de paquetes de tu distribución. La disponibilidad de comandos opcionales se consulta con `widgetctl catalog` y los manifiestos.

## Compilar, probar e instalar

```sh
git clone https://github.com/MagusCat/tinyWidgets.git
cd tinyWidgets
./scripts/build.sh
./scripts/test.sh
./scripts/install.sh
```

Los tres scripts aceptan `--offline` cuando las dependencias de Cargo ya están en caché. `build.sh` genera binario y puente CSS de producción en `target/release/`. `test.sh` compila un binario de depuración con un transporte de prueba; ese binario nunca se instala.

Instalación únicamente para el usuario actual:

- `~/.local/bin/widgetctl`: entrada pública.
- `~/.local/lib/randly-widgets/`: gestor Rust y puente CSS.
- `~/.local/lib/randly_widgets/`: editor, proveedores y herramientas Python.
- `~/.config/eww/{widgets,shared}`: módulos y recursos.
- `~/.local/state/tinyWidgets/install-backups/`: respaldos de archivos reemplazados y manifiesto.

Las instancias, perfiles, preferencias y módulos adicionales existentes se conservan. Los archivos de módulos incluidos en este repositorio sí se actualizan y se respaldan. Una configuración Eww ajena se rechaza antes de copiar archivos. No se reinicia el escritorio durante la instalación. Para actualizar módulos propios, modifica primero su código en este repositorio y reinstala.

En tu sesión Wayfire, después de instalar:

```sh
~/.local/bin/widgetctl reload
~/.local/bin/widgetctl editor
```

En una instalación nueva el catálogo comienza sin instancias; agrégalas desde el editor. Para iniciar con la sesión, añade `~/.local/bin/widgetctl start` al inicio de Wayfire. Añade `~/.local/bin` a `PATH` si quieres omitir la ruta completa.

## Uso

```sh
widgetctl catalog
widgetctl manager-status
widgetctl add cat --id gato
widgetctl set gato x=80 y=100
widgetctl duplicate gato
widgetctl disable gato
widgetctl remove gato2
widgetctl preview-anim vortex fade
widgetctl theme
widgetctl reload
widgetctl stop
```

`theme` aplica únicamente colores: no abre, cierra ni reposiciona ventanas. `reload` valida y aplica cambios estructurales de módulos; puede cerrar y volver a abrir las ventanas. El editor filtra **Global** para mostrar únicamente las instancias globales; al seleccionar un workspace muestra sus instancias y las globales.

## Colores del fondo

Para Matugen, usa el fragmento de [docs/matugen.toml](docs/matugen.toml) en tu configuración, conservando tu plantilla actual. La salida SCSS debe incluir las variables de [eww/_colors.scss](eww/_colors.scss).

La paleta del perfil predeterminado se escribe en `~/.local/state/randly-widgets/palette.scss`, fuera del directorio observado por Eww. El hook ejecuta `widgetctl theme`. El gestor compila y valida CSS y el puente lo aplica en el hilo GTK. Una paleta inválida conserva el último CSS válido. **No uses `widgetctl reload` en el hook del wallpaper**: provocaría validaciones visibles y reapertura de widgets.

Para perfiles alternativos (`widgetctl --config /ruta/al/perfil ...`), la paleta se toma de `_colors.scss` dentro del perfil; la separación del archivo observado sólo está implementada para el perfil predeterminado.

## Recursos de cada componente

Los recursos incluidos viven en `widgets/<tipo>/assets/` y se declaran en la lista `assets` de su manifiesto. `@ASSETS@` en Yuck/SCSS se resuelve al directorio del propio componente; los proveedores usan `ctx.asset("archivo.png")`. Instalar la carpeta del componente incluye sus recursos, sin copias manuales ni dependencias de widgets vecinos. El validador detecta archivos faltantes y rutas que escapan del componente.

Los avatares descargados de GitHub usan caché propia por perfil en `$XDG_CACHE_HOME/tinyWidgets/<perfil>/github` (por defecto `~/.cache`), conservan los datos antiguos durante la migración y muestran un recurso incluido cuando no hay avatar. Las fotos e imágenes personales siguen siendo entradas configurables del usuario.

## Modularidad y documentación

- [Arquitectura y extensión](docs/ARCHITECTURE.md): responsabilidades, archivos y contrato de un módulo.
- [Desarrollo y Git](CONTRIBUTING.md): pruebas, commits y sincronización remota.
- [Plan de trabajo](docs/ROADMAP.md): migración y pendientes.

## Limitaciones

- La integración de workspaces depende del IPC de Wayfire. Otros compositores no están implementados.
- Eww comparte proceso entre los widgets de un mismo perfil; un fallo del renderizador puede afectar a todo ese perfil. El aislamiento de opciones/proveedores no equivale a procesos de render separados.
- El editor, proveedores, catálogo, compilación Yuck y validación gráfica siguen en Python. El gestor de ciclo de vida, sincronización, movimiento y paleta está en Rust.
- El puente de colores depende de GTK3 y se carga con `LD_PRELOAD` sólo en el Eww de este perfil. No es una API oficial de temas de Eww y necesita comprobarse al actualizarlo.
- La validación gráfica necesita una sesión Wayland real y abre ventanas temporales. No se ejecuta al cambiar únicamente la paleta.
- Mover o redimensionar puede requerir una operación `eww open` sobre la ventana existente. No se garantiza ausencia total de saltos en todas las versiones del compositor.
- El nuevo gestor aún tiene diferencias con el motor anterior: orden aleatorio y jitter de cascada, y transición OUT antes de una recarga completa, pendientes de paridad.
- Los widgets de comandos ejecutan código del usuario: usa módulos y comandos de confianza. No existe un sandbox para proveedores.
- Los recursos pixel art existentes no tienen aún un inventario de procedencia/licencias. No se ha asignado una licencia general al repositorio.
