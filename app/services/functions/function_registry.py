from .implementations.hangup import hangup
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

registered_functions = [
    hangup,
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
    transfer_to_group]


