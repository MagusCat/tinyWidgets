# Roadmap

## Implementado

- [x] Catálogo modular por manifiesto y estilos acotados.
- [x] Assets incluidos por componente, inventario validado y caché de GitHub aislada por perfil.
- [x] Editor GTK con perfiles, edición y filtro Global.
- [x] Gestor Rust para procesos, workspaces, sincronización, instancias y cuadros de movimiento.
- [x] Cambio de paleta sin recarga estructural de Eww.
- [x] Scripts de compilación, instalación con respaldo y pruebas automatizadas.

## Validación y paridad inmediata

- [ ] Revisar visualmente el gestor Rust en la sesión real: wallpaper, arrastre, entrada y salida, tamaños dinámicos y cambios rápidos de workspace.
- [ ] Medir RAM, CPU y latencia del editor con 8, 20, 50 y 100 instancias.
- [ ] Igualar orden aleatorio/jitter y salida animada de recargas del motor anterior.
- [ ] Comprobar puente CSS con otras compilaciones compatibles de Eww/GTK.
- [ ] Añadir integración gráfica reproducible y CI con dependencias GTK.
- [ ] Obtener historial remoto y reconciliar la rama local antes del primer push autorizado.

## Siguiente etapa

- [ ] Migrar scheduler de proveedores y caché de opciones a Rust manteniendo el editor Python.
- [ ] Unificar opciones duplicadas del motor anterior después de comprobar paridad.
- [ ] Separar contratos del editor de los detalles del gestor.
- [ ] Reversión automática de una instalación completa.
- [ ] Aislar la paleta externa también en perfiles alternativos.
- [ ] Inventario y licencia de recursos y licencia general del proyecto.

## Después

- [ ] Mejorar API, música y procesos según las decisiones del catálogo.
- [ ] Importación/exportación de perfiles sin rutas personales.
- [ ] Sprites/tilesets para pixel art; prioridad baja.

No se reemplazará el editor por Rust durante esta etapa.
