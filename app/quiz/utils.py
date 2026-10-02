"""
app/quiz/utils.py — Scoring and helper utilities for the quiz blueprint.

Scoring is ALWAYS performed server-side. The client only sends raw selections;
the correct option is looked up from the database here.
"""

from app.models import db, Quiz, Question, Option


def calculate_score(quiz_id: int, answers: dict) -> tuple[int, int]:
    """
    Compute the earned score and total possible points for a quiz submission.

    Args:
        quiz_id: Primary key of the Quiz being scored.
        answers: Mapping of {str(question_id): str(option_id)} from the client.
                 The client never sees which option is correct — we check here.

    Returns:
        (earned_points, total_possible_points)
    """
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
        return 0, 0

    earned = 0
    total = 0

    for question in quiz.questions:
        total += question.points
        selected_option_id = answers.get(str(question.id))
        if selected_option_id is None:
            continue   # Question was skipped

        correct = question.correct_option
        if correct and str(correct.id) == str(selected_option_id):
            earned += question.points

    return earned, total


def format_time(seconds: int) -> str:
    """
    Convert a duration in seconds to a human-readable MM:SS string.

    Example:
        format_time(125) → "2:05"
    """
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"
