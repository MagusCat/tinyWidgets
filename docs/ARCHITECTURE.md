# Arquitectura

## Responsabilidades

| Componente | Responsabilidad |
| --- | --- |
| `manager/src/io.rs` | Rutas por perfil, escrituras atómicas, locks, Eww e IPC Wayfire |
| `manager/src/runtime.rs` | Ventanas deseadas/reales, posiciones guardadas, apertura, cierre y procesos del perfil |
| `manager/src/watch.rs` | Eventos de workspace y buzón del editor; un trabajador serializado |
| `manager/src/instances.rs` | Altas, bajas y cambios de instancias sin perder metadatos adicionales |
| `manager/src/motion.rs` | Cuadros de transforms y revelado nativos; protección por token |
| `manager/src/theme.rs` | SCSS → CSS, validación GTK y publicación fuera del árbol observado |
| `theme-bridge/` | Cambio de proveedor CSS en el hilo GTK del Eww correspondiente |
| `python/randly_widgets/editor/` | Editor GTK; IPC fuera del hilo de dibujo |
| `python/randly_widgets/composer.py` | Generaciones inmutables de Yuck/SCSS, validación y publicación |
| `python/randly_widgets/jobs.py` | Proveedores, hasta cuatro tareas concurrentes |
| `eww/widgets/<tipo>/` | Contrato y código independiente por tipo |

Hay tres listeners por perfil: datos, opciones y cuadros de movimiento. La frecuencia del movimiento no provoca una reevaluación de todas las opciones. El editor envía peticiones coalescidas y recibe ACK del gestor. Los cambios de workspace invalidan trabajo anterior; no se adivina un destino si el compositor no responde. Una respuesta vacía de Eww se contrasta con superficies reales antes de asumir que una ventana desapareció.

Las generaciones se publican después de validación gráfica; una falla durante aplicación intenta restaurar la generación anterior. Las escrituras de instancias usan lock y reemplazo atómico. La instalación respalda cada archivo reemplazado, pero todavía no ofrece una reversión automática de toda la instalación.

## Añadir un tipo

```sh
widgetctl new mi-widget
```

Se crea en la configuración instalada. Para versionarlo, copia esa carpeta a `eww/widgets/mi-widget/` en el repositorio y continúa allí.

Cada carpeta contiene:

- `manifest.json`: ID, versión, tamaño, opciones, intervalo, dependencias e información inicial.
- `view.yuck`: widget/ventana con prefijo `rw-<tipo>`.
- `style.scss`: selectores limitados a `.rw-desktop.rw-<tipo>`.
- `assets/`: recursos incluidos; declarar sus nombres relativos en `manifest.json` con `"assets": ["imagen.png"]`. No se comparte carpeta global ni se leen recursos de otro widget.
- `provider.py`: opcional; recibe un contexto de la instancia y devuelve datos JSON.

Usa `cat` como ejemplo simple y `api` para opciones. No declares listeners globales desde un módulo ni escribas estado de otra instancia. Los proveedores no deben importar ni modificar el editor. Los estilos se rechazan si escapan a la raíz del módulo; no añadas animaciones CSS de entrada/salida.

```sh
widgetctl validate mi-widget
widgetctl validate mi-widget --graphics
widgetctl reload
```

Las pruebas estructurales no sustituyen la revisión de tamaño, recorte, teclado y transiciones en Wayfire.

## Archivos personales

No se versionan `instances.json` del usuario, perfiles, tareas, hábitos, credenciales, contadores de API, fotos, estado ni generaciones. `eww/instances.json` es un ejemplo vacío; la instalación nunca sobrescribe las instancias existentes. Los nombres internos `randly_widgets` y `randly-widgets` se conservan para compatibilidad con los dotfiles.

## Contrato de recursos

`@ASSETS@/imagen.png` en vistas y estilos apunta sólo a `widgets/<tipo>/assets/imagen.png`. Un proveedor obtiene esa misma ruta con `ctx.asset("imagen.png")`, que exige que esté declarada. Se rechazan archivos inexistentes, rutas absolutas, escapes con `..` y enlaces que salen del componente. El instalador copia recursivamente los recursos junto con el módulo. Para actualizar una instalación existente no elimina la antigua carpeta global: puede seguir siendo utilizada por una generación aún activa o datos propios; las generaciones nuevas ya no dependen de ella.

Recursos remotos deben tener gestión automática de caché, tiempos de espera y fallback incluido; no descargar recursos obligatorios durante la instalación. GitHub es el primer caso: caché por perfil/componente y fallback local independiente del cofre. Las entradas personales como fotos permanecen configurables y no se distribuyen con el componente.
