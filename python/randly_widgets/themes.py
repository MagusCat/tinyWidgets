"""Shared style choices; colors are roles from the active wallpaper palette."""
SKINS=['bento','minimal','clean','pixel','monochrome','retro','zsh','gnome','terminal']
BACKGROUNDS=['surface','deep','raised','primary','secondary','tertiary','blend','transparent']
BACKGROUND_LABELS={'surface':'Superficie','deep':'Fondo profundo','raised':'Superficie elevada',
                   'primary':'Primario','secondary':'Secundario','tertiary':'Terciario','blend':'Mezcla de acentos','transparent':'Transparente'}
FX=['none','glow','float','float3d','pulse','border','halo','prism','shimmer','heartbeat','focus','scan']
FX_LABELS={'halo':'Halo','prism':'Prisma','shimmer':'Destello suave','heartbeat':'Latido','focus':'Enfoque al pasar','scan':'Barrido retro'}
FX_DESCRIPTIONS={'halo':'Aura suave sin mover el contenido.','prism':'Borde que recorre los tres acentos de la paleta.',
    'shimmer':'Brillo gradual en títulos e iconos.','heartbeat':'Doble latido de los iconos.',
    'focus':'Borde y luz únicamente al pasar el cursor.','scan':'Barrido de luz sobre texto e iconos, sin franjas de fondo.'}

def normalize_background(value):
    aliases={'global':'global','heredar':'global','primario':'primary','secundario':'secondary',
             'terciario':'tertiary','transparente':'transparent'}
    value=str(value or 'surface').lower()
    return value if value in BACKGROUNDS else aliases.get(value,'surface')
