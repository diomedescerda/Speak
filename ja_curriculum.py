import random
import re
from typing import Any, Dict, List, Optional

JA_STAGES: Dict[int, Dict[str, Any]] = {
    1: {
        "stage": 1,
        "name": "Stage 1: First Steps & Survival (Early N5)",
        "short_name": "Stage 1 · Early N5",
        "target_seconds": 25,
        "grammar_scope": "Polite present/future (です / ます), basic particles (は, を, に, で, の), simple likes (〜が好きです), requests (〜をください).",
        "topics": [
            {
                "id": "s1_self_intro",
                "title": "Self-Introduction & What I Do",
                "scenario": "Introduce yourself politely to a new Japanese acquaintance: your name, where you are from/live, and what you do.",
                "focus_grammar": "〜は〜です / 〜から来[き]ました",
            },
            {
                "id": "s1_morning_routine",
                "title": "My Morning Routine",
                "scenario": "Describe when you wake up every morning, what you drink or eat, and when you start work.",
                "focus_grammar": "〜時[じ]に〜ます / それから〜ます",
            },
            {
                "id": "s1_favorite_food",
                "title": "Favorite Food & Drinks",
                "scenario": "Talk about a food and a drink you really like, and how often you have them.",
                "focus_grammar": "〜が好[す]きです / よく〜を食[た]べます",
            },
            {
                "id": "s1_today_weather",
                "title": "Today's Weather & My Mood",
                "scenario": "Describe what the weather is like today and how you are feeling right now.",
                "focus_grammar": "今日[きょう]は〜です / とても〜です",
            },
            {
                "id": "s1_ordering_cafe",
                "title": "Ordering at a Tokyo Cafe",
                "scenario": "Order a drink and something to eat at a cafe, ask for the size or dine-in, and thank the staff.",
                "focus_grammar": "〜をください / 〜をお願[ねが]いします",
            },
            {
                "id": "s1_weekend_plans",
                "title": "Simple Weekend Plans",
                "scenario": "Share where you will go or what you will do this coming weekend and with whom.",
                "focus_grammar": "週末[しゅうまつ]は〜に行[い]きます / 〜と〜をします",
            },
            {
                "id": "s1_workspace_items",
                "title": "Things on My Desk",
                "scenario": "Describe two or three items on your desk right now and which one you use every day.",
                "focus_grammar": "〜に〜があります / 毎日[まいにち]〜を使[つか]います",
            },
        ],
    },
    2: {
        "stage": 2,
        "name": "Stage 2: Daily Life & Past Experiences (Mid N5)",
        "short_name": "Stage 2 · Mid N5",
        "target_seconds": 35,
        "grammar_scope": "Past tense (〜ました / 〜ませんでした), i-adjective and na-adjective past & connectors (〜かったです / 〜くて), listing actions (〜たり〜たりします).",
        "topics": [
            {
                "id": "s2_yesterday",
                "title": "What I Did Yesterday",
                "scenario": "Recount 2 or 3 things you did yesterday from morning to evening and how your day felt.",
                "focus_grammar": "昨日[きのう]は〜ました / 〜て、〜ました",
            },
            {
                "id": "s2_hobbies",
                "title": "How I Spend My Days Off",
                "scenario": "Give examples of activities you usually mix and match on your days off.",
                "focus_grammar": "〜たり、〜たりします",
            },
            {
                "id": "s2_recent_meal",
                "title": "A Good Meal I Had Recently",
                "scenario": "Talk about something tasty you ate recently, where you ate it, and what it was like.",
                "focus_grammar": "〜を食[た]べました / 〜くておいしかったです",
            },
            {
                "id": "s2_commute_work",
                "title": "Working From Home vs. Going Out",
                "scenario": "Describe where you usually work or study and why you find that place comfortable.",
                "focus_grammar": "〜で仕事[しごと]をします / 〜は静[しず]かで〜です",
            },
            {
                "id": "s2_shopping",
                "title": "Something Useful I Bought",
                "scenario": "Talk about an item or gadget you bought recently and how it helps you.",
                "focus_grammar": "〜を買[か]いました / とても便利[べんり]です",
            },
            {
                "id": "s2_town_description",
                "title": "Describing My City or Neighborhood",
                "scenario": "Describe the atmosphere of your city or neighborhood using connected adjectives.",
                "focus_grammar": "私[わたし]の町[まち]は〜くて、〜です",
            },
            {
                "id": "s2_learning_japanese",
                "title": "How I Study Japanese Every Day",
                "scenario": "Explain how you are practicing Japanese recently and how it feels so far.",
                "focus_grammar": "毎日[まいにち]〜ています / 少[すこ]しむずかしいですが楽[たの]しいです",
            },
        ],
    },
    3: {
        "stage": 3,
        "name": "Stage 3: Desires, Reasons & Ongoing Actions (Complete N5)",
        "short_name": "Stage 3 · Complete N5",
        "target_seconds": 45,
        "grammar_scope": "Expressing desires (〜たいです), giving reasons (〜から / 〜ので), ongoing actions/states (〜ています), polite invitations (〜ませんか).",
        "topics": [
            {
                "id": "s3_why_japanese",
                "title": "Why I Want to Speak Japanese",
                "scenario": "Explain your personal reason for learning Japanese and what you want to do with it.",
                "focus_grammar": "〜から、日本語[にほんご]を話[はな]したいです",
            },
            {
                "id": "s3_japan_travel",
                "title": "Where I Want to Visit in Japan",
                "scenario": "Name a city or place in Japan you want to visit and two things you want to do there.",
                "focus_grammar": "〜に行[い]きたいです / そこで〜たいです",
            },
            {
                "id": "s3_current_project",
                "title": "What I Am Working On Lately",
                "scenario": "Describe a project, skill, or habit you are currently working on every week.",
                "focus_grammar": "最近[さいきん]、〜ています / 〜のでおもしろいです",
            },
            {
                "id": "s3_favorite_season",
                "title": "My Favorite Season & Why",
                "scenario": "Say which season you like best and explain the reason using weather or activities.",
                "focus_grammar": "一番[いちばん]好[す]きな季節[きせつ]は〜です。〜からです",
            },
            {
                "id": "s3_recommendation",
                "title": "Recommending a Show, Game, or Book",
                "scenario": "Recommend a favorite movie, anime, game, or book to a friend and explain why it's great.",
                "focus_grammar": "〜がおすすめです / 〜からとてもおもしろいです",
            },
            {
                "id": "s3_weekend_invitation",
                "title": "Inviting a Friend to Hang Out",
                "scenario": "Suggest a weekend activity to a Japanese friend, propose a time/place, and invite them warmly.",
                "focus_grammar": "一緒[いっしょ]に〜ませんか？ / 〜ましょう",
            },
            {
                "id": "s3_health_habit",
                "title": "Something I Do for My Energy & Health",
                "scenario": "Share one routine you do to stay healthy or focused and why you do it.",
                "focus_grammar": "健康[けんこう]のために〜ています",
            },
        ],
    },
    4: {
        "stage": 4,
        "name": "Stage 4: Opinions, Comparisons & Plans (Bridge N5→N4)",
        "short_name": "Stage 4 · N5→N4 Bridge",
        "target_seconds": 55,
        "grammar_scope": "Stating opinions (〜と思います), intentions/plans (〜つもりです), past experiences (〜たことがあります), comparisons (AよりBのほうが〜), advice (〜たほうがいいです).",
        "topics": [
            {
                "id": "s4_opinion_tech",
                "title": "My Thoughts on Technology & AI",
                "scenario": "Share what you think about using AI or technology in daily work and why.",
                "focus_grammar": "〜と思[おも]います / 〜のは便利[べんり]です",
            },
            {
                "id": "s4_future_goal",
                "title": "A Personal Goal for This Year",
                "scenario": "Talk about something specific you intend to accomplish this year and how you plan to do it.",
                "focus_grammar": "今年[ことし]は〜つもりです",
            },
            {
                "id": "s4_ever_tried",
                "title": "A Memorable Experience I Have Had",
                "scenario": "Talk about an interesting place you have visited or something cool you have tried before.",
                "focus_grammar": "〜たことがあります / また〜たいと思[おも]います",
            },
            {
                "id": "s4_compare_options",
                "title": "Comparing Two Things I Enjoy",
                "scenario": "Compare two tools, foods, or hobbies and explain why you prefer one over the other.",
                "focus_grammar": "AよりBのほうが〜です / なぜなら〜からです",
            },
            {
                "id": "s4_giving_advice",
                "title": "Advice for a Beginner Programmer",
                "scenario": "Give encouraging advice to someone who is just starting to learn programming or a new skill.",
                "focus_grammar": "まず〜たほうがいいと思[おも]います",
            },
            {
                "id": "s4_solving_problem",
                "title": "When Something Went Wrong & How I Fixed It",
                "scenario": "Describe a small problem you ran into recently when working and what you did when it happened.",
                "focus_grammar": "〜時[とき]、〜ましたが、〜ました",
            },
            {
                "id": "s4_ideal_day",
                "title": "My Ideal Free Day",
                "scenario": "Explain what you would love to do if you had a completely free day with no obligations.",
                "focus_grammar": "もし時間[じかん]があったら、〜たいです",
            },
        ],
    },
    5: {
        "stage": 5,
        "name": "Stage 5: Connected Storytelling & Nuance (N4+)",
        "short_name": "Stage 5 · N4+ Conversational",
        "target_seconds": 65,
        "grammar_scope": "Change of ability/habit (〜ようになりました), trying things out (〜てみます), contrasting nuances (〜し、〜し / 〜けど / 一方で), conditionals (〜たら / 〜ば).",
        "topics": [
            {
                "id": "s5_turning_point",
                "title": "How I Got Into Software & Tech",
                "scenario": "Tell the story of what sparked your interest in computers or coding and how it changed your life.",
                "focus_grammar": "きっかけは〜でした / それから〜ようになりました",
            },
            {
                "id": "s5_pros_cons",
                "title": "Both Sides of Remote Work",
                "scenario": "Discuss one big advantage and one challenge of working remotely from your perspective.",
                "focus_grammar": "〜し、〜し、便利[べんり]ですが、ときどき〜と思[おも]います",
            },
            {
                "id": "s5_overcoming_difficulty",
                "title": "Something That Was Hard at First",
                "scenario": "Talk about something that felt very difficult when you started, but that you can do now.",
                "focus_grammar": "最初[さいしょ]は〜ませんでしたが、今[いま]は〜ようになりました",
            },
            {
                "id": "s5_cultural_curiosity",
                "title": "What Fascinates Me About Japanese Culture",
                "scenario": "Explain a specific aspect of Japanese culture, food, or design that interests you deeply.",
                "focus_grammar": "〜に興味[きょうみ]があります / 一度[いちど]〜てみたいです",
            },
            {
                "id": "s5_habit_change",
                "title": "A Habit That Improved My Daily Life",
                "scenario": "Describe a habit you started trying and how your daily life changed as a result.",
                "focus_grammar": "〜ようにしてから、〜なりました",
            },
            {
                "id": "s5_teaching_concept",
                "title": "Explaining My Favorite Tool Simply",
                "scenario": "Explain a piece of software or tool you love to a non-technical Japanese friend.",
                "focus_grammar": "〜というのは、〜ためのツールです",
            },
            {
                "id": "s5_reflection_progress",
                "title": "Reflecting on My Japanese Speaking Journey",
                "scenario": "Reflect on how your Japanese speaking has grown and what you want to challenge next.",
                "focus_grammar": "少[すこ]しずつ話[はな]せるようになってきました / これからも〜つもりです",
            },
        ],
    },
}


def get_stage_info(stage: int) -> Dict[str, Any]:
    s = max(1, min(5, int(stage)))
    return JA_STAGES[s]


def pick_ja_topic(stage: int, used_topics: List[str]) -> Dict[str, Any]:
    stage_info = get_stage_info(stage)
    topics = stage_info["topics"]
    unused = [t for t in topics if t["id"] not in set(used_topics)]
    if unused:
        # Pick the first unused topic in curriculum order so progression feels structured
        chosen = unused[0]
    else:
        chosen = random.choice(topics)
    return {
        "stage": stage_info["stage"],
        "stage_name": stage_info["name"],
        "short_name": stage_info["short_name"],
        "target_seconds": stage_info["target_seconds"],
        "grammar_scope": stage_info["grammar_scope"],
        "topic": chosen,
    }


def strip_furigana(text: str) -> str:
    """Remove inline furigana brackets like 漢字[かんじ] -> 漢字 for TTS and matching."""
    if not text:
        return ""
    return re.sub(r"\[[^\]]+\]", "", text)
