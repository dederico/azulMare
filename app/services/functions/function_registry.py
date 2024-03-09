from .implementations.get_credit_card_options import get_credit_card_options
from .implementations.weather import get_current_weather
from .implementations.hangup import hangup
from .implementations.save_selection import save_client_selection
from .implementations.identify import get_customer_identity
from .implementations.redirect import redirect_call
registered_functions = [get_current_weather, hangup, save_client_selection, redirect_call]
