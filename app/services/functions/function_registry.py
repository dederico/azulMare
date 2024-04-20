from .implementations.get_credit_card_options import get_credit_card_options
from .implementations.weather import get_current_weather
from .implementations.hangup import hangup
from .implementations.identify import get_customer_identity

registered_functions = [get_credit_card_options, hangup, get_current_weather, get_customer_identity]