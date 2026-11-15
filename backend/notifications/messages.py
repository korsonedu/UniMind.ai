from core.interface_language import ui_text


def notification_text(notification, language=None):
    if notification.ntype != 'system' or notification.title == '学习健康度提醒':
        return ui_text(notification.title, language), ui_text(notification.content, language)
    return notification.title, notification.content
