"""Parsing and saving the quiz form, shared by the quiz master and admin pages."""

from app.models import GameSession, Option, Question, Quiz, TeamAnswer, db

MAX_QUESTIONS = 50
OPTIONS_PER_QUESTION = 4


def blank_form() -> dict:
    return {
        "title": "",
        "description": "",
        "category": "General",
        "difficulty": "easy",
        "time_limit_seconds": 180,
        "question_seconds": 30,
        "is_published": False,
        "owner_id": None,
        "questions": [_blank_question()],
    }


def _blank_question() -> dict:
    return {"id": None, "text": "", "options": [""] * OPTIONS_PER_QUESTION, "correct": 0}


def form_from_quiz(quiz: Quiz) -> dict:
    questions = []
    for question in quiz.questions:
        options = question.options.all()[:OPTIONS_PER_QUESTION]
        texts = [option.text for option in options]
        questions.append({
            "id": question.id,
            "text": question.text,
            "options": texts + [""] * (OPTIONS_PER_QUESTION - len(texts)),
            "correct": next((i for i, option in enumerate(options) if option.is_correct), None),
        })
    first = quiz.questions.first()
    return {
        "title": quiz.title,
        "description": quiz.description or "",
        "category": quiz.category or "General",
        "difficulty": quiz.difficulty or "easy",
        "time_limit_seconds": quiz.time_limit_seconds,
        "question_seconds": first.time_limit_seconds if first else 30,
        "is_published": quiz.is_published,
        "owner_id": quiz.created_by,
        "questions": questions or [_blank_question()],
    }


def parse_form(form) -> tuple[dict, list[str]]:
    """The submitted values (so the page can be shown again without losing work) and any errors."""
    errors = []

    def number(name: str, label: str, default: int, low: int, high: int):
        raw = form.get(name, "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            value = None
        if value is None or not low <= value <= high:
            errors.append(f"{label} must be a whole number from {low} to {high}.")
            return raw
        return value

    data = {
        "title": form.get("title", "").strip(),
        "description": form.get("description", "").strip(),
        "category": form.get("category", "").strip() or "General",
        "difficulty": form.get("difficulty", "easy").strip(),
        "time_limit_seconds": number("time_limit_seconds", "Self-paced time limit", 180, 10, 7200),
        "question_seconds": number("question_seconds", "Seconds per question", 30, 5, 600),
        "is_published": "is_published" in form,
        "owner_id": form.get("owner_id", type=int),
        "questions": [],
    }
    if not data["title"]:
        errors.append("Quiz title is required.")
    if len(data["title"]) > 128:
        errors.append("The quiz title can be at most 128 characters.")
    if len(data["category"]) > 64:
        errors.append("The category can be at most 64 characters.")
    if data["difficulty"] not in Quiz.DIFFICULTY_CHOICES:
        data["difficulty"] = "easy"

    count = form.get("question_count", default=1, type=int)
    if not 1 <= count <= MAX_QUESTIONS:
        errors.append(f"A quiz must have between 1 and {MAX_QUESTIONS} questions.")
    for idx in range(min(max(count, 1), MAX_QUESTIONS)):
        question = {
            "id": form.get(f"question_id_{idx}", type=int),
            "text": form.get(f"question_text_{idx}", "").strip(),
            "options": [form.get(f"option_text_{idx}_{o}", "").strip() for o in range(OPTIONS_PER_QUESTION)],
            "correct": form.get(f"correct_option_{idx}", type=int),
        }
        data["questions"].append(question)

        label = f"Question {idx + 1}"
        if not question["text"]:
            errors.append(f"{label} needs its question text.")
        if sum(bool(text) for text in question["options"]) < 2:
            errors.append(f"{label} needs at least two answer options.")
        if any(len(text) > 256 for text in question["options"]):
            errors.append(f"{label}: answer options can be at most 256 characters.")
        correct = question["correct"]
        if correct not in range(OPTIONS_PER_QUESTION) or not question["options"][correct]:
            errors.append(f"Choose the correct answer for question {idx + 1}.")
    return data, errors


def active_game(quiz: Quiz):
    """A game of this quiz that is being played now, or None."""
    return quiz.sessions.filter(GameSession.state.in_(GameSession.IN_PROGRESS_STATES)).first()


def save(quiz: Quiz, data: dict) -> None:
    """Write validated form data to a new or existing quiz and commit.

    Existing questions and options are updated in place, so answers recorded in earlier
    games keep pointing at real rows. Answers to a removed question are removed with it.
    """
    for field in ("title", "description", "category", "difficulty", "time_limit_seconds", "is_published"):
        setattr(quiz, field, data[field])
    db.session.add(quiz)
    db.session.flush()

    existing = {question.id: question for question in quiz.questions.all()}
    next_in_round: dict[int, int] = {}
    last_round = 1
    for idx, item in enumerate(data["questions"]):
        question = existing.pop(item["id"], None)
        if question is None:
            # A new question joins the round of the question before it.
            question = Question(quiz_id=quiz.id, round_number=last_round, points=10)
            db.session.add(question)
        last_round = question.round_number or 1
        next_in_round[last_round] = next_in_round.get(last_round, 0) + 1
        question.text = item["text"]
        question.order_index = idx
        question.order_in_round = next_in_round[last_round]
        question.time_limit_seconds = data["question_seconds"]
        db.session.flush()
        _save_options(question, item["options"], item["correct"])

    for question in existing.values():
        TeamAnswer.query.filter_by(question_id=question.id).delete()
        db.session.delete(question)
    db.session.commit()


def _save_options(question: Question, texts: list[str], correct: int) -> None:
    current = question.options.all()
    for position, text in enumerate(texts):
        option = current[position] if position < len(current) else None
        if not text:
            if option is not None:
                TeamAnswer.query.filter_by(option_id=option.id).update({"option_id": None})
                db.session.delete(option)
            continue
        if option is None:
            option = Option(question_id=question.id)
            db.session.add(option)
        option.text = text
        option.order_index = position
        option.is_correct = position == correct
