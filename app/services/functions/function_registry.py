#from .implementations.hangup import hangup
from .implementations.save_selection import save_client_selection
from .implementations.get_directorio import get_funcionarios
from .implementations.get_centros_comunitarios import get_centros_comunitarios
from .implementations.get_carta_radicacion import get_carta_radicacion
from .implementations.get_centros_bienestar import get_centros_bienestar
from .implementations.get_centros_reciclaje import get_centros_reciclaje
from .implementations.get_consulta_multas_transito import get_consultas_multas_transito
from .implementations.get_denuncia_maltrato_animal import get_denuncia_maltrato_animal
from .implementations.get_empleo import get_empleo
from .implementations.get_parquimetros import get_parquimetros
from .implementations.get_gimnasios import get_gimnasios
from .implementations.transfer_message_event import transfer_to_group
from .implementations.get_voluntarios import get_voluntarios
from .implementations.get_urls import get_urls
from .implementations.get_ubicaciones import get_ubicaciones
from .implementations.get_parques_emblematicos import get_parques_emblematicos
from .implementations.get_dif import get_dif
from .implementations.get_desarrollo_urbano import get_desarrollo_urbano
from .implementations.get_seguridad import get_seguridad
from .implementations.get_inapam import get_inapam
from .implementations.get_apoyo_alimentario import get_apoyo_alimentario
from .implementations.get_salud_publica import get_salud_publica
from .implementations.get_restaurant_week import get_restaurant_week
from .implementations.get_san_pedro_de_pinta import get_san_pedro_de_pinta
from .implementations.get_basura_vegetal import get_basura_vegetal
from .implementations.get_ks import get_ks
from .implementations.get_san_pedro_de_pinta_patrocinadores import get_san_pedro_de_pinta_patrocinadores
from .implementations.get_basura_vegetal import get_basura_vegetal
from .implementations.get_activaciones_san_pedro_de_pinta import get_activaciones_san_pedro_de_pinta
from .implementations.get_bienestar import get_bienestar
from .implementations.get_pasaportes import get_pasaportes
from .implementations.get_registro_civil import get_registro_civil
from .implementations.get_miercoles_ciudadano import get_miercoles_ciudadano
from .implementations.get_mercado_fregoneria import get_mercado_fregoneria
from .implementations.get_licencias_temporales import get_licencia_provisional
from .implementations.get_licencia_chofer import get_licencia_chofer
from .implementations.get_government_location import get_nearest_office
from .implementations.nearest_office import find_nearest_government_office
from .implementations.get_circuitos_de_transporte import get_circuitos_de_transporte
from .implementations.get_inah import get_inah
from .implementations.get_jueces_auxiliares import get_jueces_auxiliares
from .implementations.get_licencia_16 import get_licencia_16
from .implementations.get_licencia_automovilista import get_licencia_automovilista
from .implementations.get_lugares_de_interes import get_lugares_de_interes
from .implementations.get_movilidad import get_movilidad
from .implementations.get_predial import get_predial


registered_functions = [
    #hangup,
    save_client_selection, 
    get_funcionarios, 
    get_centros_comunitarios, 
    get_carta_radicacion, 
    get_centros_bienestar, 
    get_centros_reciclaje, 
    get_consultas_multas_transito,
    get_denuncia_maltrato_animal,
    get_empleo,
    get_parquimetros,
    get_gimnasios,
    get_voluntarios,
    get_urls,
    get_ubicaciones,
    get_parques_emblematicos,
    get_dif,
    get_desarrollo_urbano,
    get_seguridad,
    get_inapam,
    get_apoyo_alimentario,
    get_salud_publica,
    get_restaurant_week,
    get_san_pedro_de_pinta,
    get_basura_vegetal,
    get_ks,
    get_san_pedro_de_pinta_patrocinadores,
    get_activaciones_san_pedro_de_pinta,
    get_bienestar,
    get_pasaportes,
    get_registro_civil,
    get_miercoles_ciudadano,
    get_mercado_fregoneria,
    get_licencia_provisional,
    get_licencia_chofer,
    transfer_to_group,
    get_nearest_office,
    find_nearest_government_office,
    get_circuitos_de_transporte,
    get_inah,
    get_jueces_auxiliares,
    get_licencia_16,
    get_licencia_automovilista,
    get_lugares_de_interes,
    get_movilidad,
    get_predial
]