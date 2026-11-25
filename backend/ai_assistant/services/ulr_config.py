"""Select the shared ULR execution mode for web and worker entry points."""
from django.conf import settings


def standalone_ulr():
    return settings.UNIMIND_LEARNING_RUNTIME == 'ulr'


def ulr_enabled():
    return standalone_ulr() or (settings.DEBUG and settings.UNIMIND_ULR_PROTOTYPE)
