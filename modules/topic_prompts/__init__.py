"""
Topic-specific prompts for Progressive Prompts Generator.
Moi chu de co 1 file Python rieng de de tuy chinh.
"""

try:
    from modules.topic_prompts.story_prompts import StoryPrompts
    from modules.topic_prompts.psychology_prompts import PsychologyPrompts
    from modules.topic_prompts.finance_history_prompts import FinanceHistoryPrompts
    from modules.topic_prompts.finance_history_vn_prompts import FinanceHistoryVNPrompts
except ImportError:
    from .story_prompts import StoryPrompts
    from .psychology_prompts import PsychologyPrompts
    from .finance_history_prompts import FinanceHistoryPrompts
    from .finance_history_vn_prompts import FinanceHistoryVNPrompts

TOPIC_MAP = {
    "story": StoryPrompts,
    "psychology": PsychologyPrompts,
    "finance_history": FinanceHistoryPrompts,
    "finance_history_vn": FinanceHistoryVNPrompts,
}


def get_topic_prompts(topic: str):
    """Lay topic prompts class theo ten topic."""
    cls = TOPIC_MAP.get(topic, StoryPrompts)
    return cls()
