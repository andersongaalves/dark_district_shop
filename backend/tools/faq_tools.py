from schemas.faq import FAQTopic
from services.faq import list_faq
from tools.catalog_tools import ToolArguments, ToolResult


class FAQArguments(ToolArguments):
    topic: FAQTopic | None = None


def consult_faq(_db, arguments: FAQArguments) -> ToolResult:
    return ToolResult(faqs=list_faq(arguments.topic))
