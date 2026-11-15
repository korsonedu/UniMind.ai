from django import template
from core.interface_language import ui_text

register = template.Library()
register.filter('ui', ui_text)
