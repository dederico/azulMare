from .implementations.get_credit_card_options import get_credit_card_options
from .implementations.weather import get_current_weather
from .implementations.hangup import hangup
from .implementations.create_google_event import create_google_event

registered_functions = [get_credit_card_options, hangup, get_current_weather, create_google_event]