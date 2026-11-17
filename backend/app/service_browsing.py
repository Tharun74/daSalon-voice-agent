"""Short, predictable replies for browsing the website's service menu."""
import re

MENU_REPLY = "Here are the services we offer. Find your feel-good — tap a service to hear more about it."
MENU_FOLLOWUP = "Is there something else you're looking for?"


def is_menu_request(text):
    text = re.sub(r"[’']", '', text.lower()).strip()
    if re.search(r'\b(dont|do not|no need to|stop|price|prices|cost|aftercare)\b', text):
        return False
    return bool(
        re.fullmatch(r'(your |the )?(services|treatments|menu)( please)?[?.!]*', text)
        or (re.search(r'\b(services|treatments|menu)\b', text)
            and re.search(r'\b(what|which|show|list|see|view|browse|offer|available|provide|tell|know|have)\b', text))
    )
