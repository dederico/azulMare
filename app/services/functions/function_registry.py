from .implementations.get_credit_card_options import get_credit_card_options
from .implementations.weather import get_current_weather
from .implementations.hangup import hangup
from .implementations.identify import get_customer_identity
from .implementations.create_google_event import create_google_event
from .implementations.date import get_current_date
# from .implementations.send_email import send_ticket_email
from .implementations.save_selection import save_client_selection
from .implementations.get_directorio import get_funcionarios
from .implementations.get_centros_comunitarios import get_centros_comunitarios

#registered_functions = [get_current_date, get_customer_identity, get_credit_card_options, hangup, get_current_weather, create_google_event] #send_ticket_email]
registered_functions = [hangup,save_client_selection, get_credit_card_options, get_funcionarios, get_centros_comunitarios]


