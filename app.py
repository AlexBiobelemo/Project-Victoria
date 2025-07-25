# ACADEMIC HONESTY NOTE

# This project was completed with the assistance of Google's Gemini AI.
# Gemini was utilized for tasks such as debugging complex issues, reviewing code
# for quality and style, refining the application's architecture, and
# implementing security best practices like CSRF protection and XSS sanitization.
# All final architectural decisions and code implementation were made by me.
# ==============================================================================


import os
import re
import random
import json
import requests
import datetime
import mistune
import bleach  # Add this import at the top of your file
import csv
import uuid
from flask_wtf.csrf import CSRFProtect
from flask import Response, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy # Assuming db is an instance of SQLAlchemy
from sqlalchemy.sql import func # Assuming you use func for something else, but not directly for export_notes
import urllib.parse
from bs4 import BeautifulSoup
from flask import render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from flask import render_template

from flask import (Flask, request, redirect, url_for, session, flash,
                   render_template, jsonify, Response)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from sqlalchemy import or_
from werkzeug.security import generate_password_hash, check_password_hash
from weasyprint import HTML

# --- App Config ---
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_super_secret_key_here'
db = SQLAlchemy(app)
OLLAMA_API_URL = os.getenv('OLLAMA_API_URL')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL')
csrf = CSRFProtect(app)



KNOWLEDGE_GRAPH = {}
TITLE_TO_ID_MAP = {}

def load_knowledge_graph():
    global KNOWLEDGE_GRAPH, TITLE_TO_ID_MAP
    try:
        with open('knowledge_graph.json', 'r') as f:
            graph_data = json.load(f)
        for topic in graph_data:
            KNOWLEDGE_GRAPH[topic['id']] = topic
            TITLE_TO_ID_MAP[topic['title'].lower().strip()] = topic['id']
        print("Knowledge graph for path logic loaded successfully.")
    except Exception as e:
        print(f"Could not load knowledge_graph.json: {e}")


load_knowledge_graph()


# DATABASE MODELS
user_badges = db.Table('user_badges',
                       db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
                       db.Column('badge_id', db.Integer, db.ForeignKey('badge.id'), primary_key=True)
                       )

class ReviewItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    next_review_at = db.Column(db.DateTime, nullable=False, default=datetime.datetime.utcnow)
    interval = db.Column(db.Integer, default=1, nullable=False) # In days

    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    topic_id = db.Column(db.String(80), db.ForeignKey('topic.id'), nullable=False)


class StepRating(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), primary_key=True)
    step_id = db.Column(db.Integer, db.ForeignKey('learning_step.id', ondelete='CASCADE'), primary_key=True)
    rating = db.Column(db.Integer, nullable=False)

    user = db.relationship('User', backref=db.backref('step_ratings', cascade="all, delete-orphan"))
    step = db.relationship('LearningStep', backref=db.backref('ratings', cascade="all, delete-orphan"))


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)  # ADDED
    first_name = db.Column(db.String(100), nullable=False)  # ADDED
    last_name = db.Column(db.String(100), nullable=False)  # ADDED
    password_hash = db.Column(db.String(120), nullable=False)
    known_topics_ids = db.Column(db.Text, nullable=False, default='')
    points = db.Column(db.Integer, default=0)
    learning_paths = db.relationship('LearningPath', backref='user', lazy=True, cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='commenter', lazy='dynamic', cascade="all, delete-orphan")
    badges = db.relationship('Badge', secondary=user_badges, lazy='subquery', backref=db.backref('users', lazy=True))
    submissions = db.relationship('ProjectSubmission', backref='author', lazy=True)
    review_items = db.relationship('ReviewItem', backref='user', lazy=True)


class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    icon = db.Column(db.String(50), nullable=False)
    points_required = db.Column(db.Integer, unique=True, nullable=False)


class ProjectSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_title = db.Column(db.String(200), nullable=False)
    project_url = db.Column(db.String(500), nullable=False)
    project_description = db.Column(db.Text, nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    learning_path_id = db.Column(db.Integer, db.ForeignKey('learning_path.id', ondelete='CASCADE'), nullable=False)
    certificate_id = db.Column(db.String(36), unique=True, nullable=True)  # ADDED


class Topic(db.Model):
    id = db.Column(db.String(80), primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    difficulty = db.Column(db.String(50))
    keywords = db.Column(db.Text)
    project_ideas = db.Column(db.Text)
    resources = db.relationship('Resource', backref='topic', lazy='dynamic')


class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    resource_title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    resource_type = db.Column(db.String(50), nullable=True)
    useful_count = db.Column(db.Integer, default=0, nullable=False)
    not_useful_count = db.Column(db.Integer, default=0, nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('learning_step.id'), nullable=True)
    topic_id = db.Column(db.String(80), db.ForeignKey('topic.id'), nullable=True)


class LearningPath(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    goal_title = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    learning_steps = db.relationship('LearningStep', backref='learning_path', lazy=True,
                                     order_by="LearningStep.step_number", cascade="all, delete-orphan")
    submission = db.relationship('ProjectSubmission', backref='path', uselist=False)  # uselist=False for one-to-one


class LearningStep(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    path_id = db.Column(db.Integer, db.ForeignKey('learning_path.id'), nullable=False)
    topic_id = db.Column(db.String(80), db.ForeignKey('topic.id'), nullable=False)
    step_title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False)
    step_number = db.Column(db.Integer, nullable=False)
    avg_rating = db.Column(db.Float, default=0.0, nullable=False)
    rating_count = db.Column(db.Integer, default=0, nullable=False)
    resources = db.relationship('Resource', backref='learning_step', lazy='subquery', cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='step', lazy='dynamic', cascade="all, delete-orphan")
    suggestions = db.relationship('ResourceSuggestion', backref='step', lazy=True)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('learning_step.id', ondelete='CASCADE'), nullable=False)


class UserNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('learning_step.id', ondelete='CASCADE'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'step_id', name='_user_step_uc'),)


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('learning_step.id', ondelete='CASCADE'), nullable=False)


class ProblemSet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.String(80), db.ForeignKey('topic.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    main_description = db.Column(db.Text, nullable=False)
    difficulty = db.Column(db.String(50))
    hints_text = db.Column(db.Text, nullable=True)
    expected_output = db.Column(db.Text, nullable=True)
    distribution_code = db.Column(db.Text, nullable=True)
    specifications_text = db.Column(db.Text, nullable=True)
    testing_description = db.Column(db.Text, nullable=True)
    submission_instructions = db.Column(db.Text, nullable=True)
    solution_url = db.Column(db.String(500), nullable=True)


class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.String(80), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(200), nullable=False)
    option_b = db.Column(db.String(200), nullable=False)
    option_c = db.Column(db.String(200), nullable=False)
    option_d = db.Column(db.String(200), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)


class ResourceSuggestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    step_id = db.Column(db.Integer, db.ForeignKey('learning_step.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    resource_type = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False)
    suggested_at = db.Column(db.DateTime(timezone=True), server_default=func.now())



# SETUP COMMANDS & HELPER FUNCTIONS
@app.cli.command("import-csv")
def import_csv_command():
    # Import Topics
    try:
        with open('topics.csv', 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Check if topic already exists
                if not Topic.query.get(row['id']):
                    topic = Topic(
                        id=row['id'],
                        title=row['title'],
                        description=row.get('description', ''),
                        difficulty=row.get('difficulty', 'beginner'),
                        keywords=row.get('keywords', ''),
                        project_ideas=row.get('project_ideas', '')
                    )
                    db.session.add(topic)
            db.session.commit()
            print("✅ Topics imported successfully.")
    except FileNotFoundError:
        print("Could not find topics.csv. Skipping.")
    except Exception as e:
        db.session.rollback()
        print(f"Error importing topics: {e}")

    # Import Resources
    try:
        with open('resources.csv', 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Check if the topic exists before adding a resource to it
                if Topic.query.get(row['topic_id']):
                    resource = Resource(
                        resource_title=row['resource_title'],
                        url=row['url'],
                        resource_type=row.get('resource_type', 'article'),
                        topic_id=row['topic_id']
                    )
                    db.session.add(resource)
            db.session.commit()
            print("✅ Resources imported successfully.")
    except FileNotFoundError:
        print("Could not find resources.csv. Skipping.")
    except Exception as e:
        db.session.rollback()
        print(f"Error importing resources: {e}")

    try:
        with open('problem_sets.csv', 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Check if this exact problem already exists to prevent duplicates
                if not ProblemSet.query.filter_by(
                        topic_id=row['topic_id'],
                        title=row['problem_title']
                ).first():
                    problem = ProblemSet(
                        # Map CSV columns to model fields
                        topic_id=row['topic_id'],
                        title=row['problem_title'],
                        main_description=row['problem_description'],
                        difficulty=row.get('difficulty'),
                        hints_text=row.get('hints'),
                        expected_output=row.get('expected_output')
                    )
                    db.session.add(problem)
            db.session.commit()
            print("✅ Problem sets imported successfully.")
    except FileNotFoundError:
        print("Could not find problem_sets.csv. Skipping.")
    except Exception as e:
        db.session.rollback()
        print(f"Error importing problem sets: {e}")


def create_review_items_for_topic(user, topic):
    # Check if review items already exist for this user and topic
    if ReviewItem.query.filter_by(user_id=user.id, topic_id=topic.id).first():
        print(f"Review items already exist for user {user.id} and topic {topic.id}.")
        return

    # Prompt the AI to generate flashcards in a specific JSON format
    prompt = (
        "You are a teacher creating flashcards. Based on the following topic title and description, "
        f"generate exactly 3 distinct Question/Answer pairs. The questions should test the core concepts. "
        f"Topic Title: {topic.title}. Description: {topic.description}. "
        "Your response MUST be a single, raw JSON object containing a key 'flashcards' which is a list of objects. "
        "Each object must have two keys: 'question' and 'answer'."
    )

    try:
        ollama_payload = {"model": OLLAMA_MODEL, "prompt": prompt, "format": "json", "stream": False}
        response = requests.post(OLLAMA_API_URL, json=ollama_payload, timeout=60)
        response.raise_for_status()
        ai_data = json.loads(response.json().get('response', '{}'))
        flashcards = ai_data.get('flashcards', [])

        for card in flashcards:
            if 'question' in card and 'answer' in card:
                review_item = ReviewItem(
                    question=card['question'],
                    answer=card['answer'],
                    next_review_at=datetime.datetime.utcnow() + datetime.timedelta(days=1), # Schedule first review for tomorrow
                    interval=1,
                    user_id=user.id,
                    topic_id=topic.id
                )
                db.session.add(review_item)

        db.session.commit()
        print(f"Successfully created {len(flashcards)} review items for topic {topic.id}.")

    except Exception as e:
        print(f"Failed to create review items for topic {topic.id}: {e}")
        db.session.rollback()


@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    print("Initialized the database.")


@app.cli.command("migrate-data")
def migrate_data_command():
    print("Starting data migration...")

    # Load topics from JSON to populate Topic table
    try:
        with open('knowledge_graph.json', 'r') as f:
            graph_data = json.load(f)
        for topic_data in graph_data:
            if not Topic.query.get(topic_data['id']):
                new_topic = Topic(
                    id=topic_data.get('id'),
                    title=topic_data.get('title'),
                    description=topic_data.get('description'),
                    difficulty=topic_data.get('difficulty'),
                    keywords=','.join(topic_data.get('keywords', [])),
                    project_ideas=','.join(topic_data.get('project_ideas', []))
                )
                db.session.add(new_topic)
                for res_data in topic_info.get('default_resources', []):
                    db.session.add(Resource(
                        learning_step=step,
                        resource_title=res_data['resource_title'],
                        url=res_data['url'],
                        resource_type=res_data.get('resource_type', 'article')
                    ))

        print("Topics and Resources migrated.")
    except Exception as e:
        db.session.rollback()
        print(f"Error migrating Topics/Resources: {e}")

    # Add Badges
    badges_to_create = [
        {'name': 'Pathfinder', 'description': 'Completed your first step.', 'icon': 'bi-compass-fill',
         'points_required': 10},
        {'name': 'Scholar', 'description': 'Reached 50 points.', 'icon': 'bi-book-half', 'points_required': 50},
        {'name': 'Master', 'description': 'Reached 250 points.', 'icon': 'bi-trophy-fill', 'points_required': 250}
    ]
    for badge_data in badges_to_create:
        if not Badge.query.filter_by(name=badge_data['name']).first():
            db.session.add(Badge(**badge_data))
    db.session.commit()
    print("Badges migrated.")
    print("Data migration successful!")


def is_admin():
    if 'user_id' not in session: return False
    user = User.query.get(session['user_id'])
    if not user:
        flash("User not found. Please log in again.", "warning")
        return redirect(url_for('login'))
    return user and user.username == 'admin'


def grant_points_and_badges(user, points_to_add):
    if not user: return
    user.points += points_to_add
    eligible_badges = Badge.query.filter(Badge.points_required <= user.points).all()
    for badge in eligible_badges:
        if badge not in user.badges:
            user.badges.append(badge)
            flash(f'New Badge Unlocked: {badge.name}!', 'success')
    db.session.commit()



# ROUTES
@app.route('/rate_step/<int:step_id>', methods=['POST'])
def rate_step(step_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'You must be logged in to rate.'}), 401

    step = LearningStep.query.get_or_404(step_id)
    user_id = session['user_id']

    # Check if the user has already rated this step
    existing_rating = StepRating.query.filter_by(user_id=user_id, step_id=step_id).first()
    if existing_rating:
        return jsonify({'success': False, 'message': 'You have already rated this step.'}), 403

    data = request.get_json()
    rating = data.get('rating')

    # Validate the rating value
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        return jsonify({'success': False, 'message': 'Invalid rating value.'}), 400

    try:
        # Create a new rating entry
        new_rating = StepRating(user_id=user_id, step_id=step_id, rating=rating)
        db.session.add(new_rating)

        # Recalculate the step's average rating
        all_ratings = [r.rating for r in step.ratings]
        step.rating_count = len(all_ratings)
        step.avg_rating = sum(all_ratings) / step.rating_count if step.rating_count > 0 else 0

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Thank you for your feedback!',
            'new_avg_rating': round(step.avg_rating, 2),
            'new_rating_count': step.rating_count
        })

    except Exception as e:
        db.session.rollback()
        print(f"Error saving rating: {e}")
        return jsonify({'success': False, 'message': 'An error occurred while saving your rating.'}), 500

@app.route('/certificate/<string:certificate_id>')
def view_certificate(certificate_id):
    submission = ProjectSubmission.query.filter_by(certificate_id=certificate_id).first_or_404()
    return render_template('certificate.html', submission=submission)


@app.route('/admin/suggestions')
def admin_suggestions():
    # Security: Only allow admins to access this page
    if not is_admin():
        flash("You do not have permission to access this page.", "danger")
        return redirect(url_for('home'))

    # Fetch all suggestions that are still pending review.
    suggestions = db.session.query(
        ResourceSuggestion,
        User.username.label('suggester_username'),
        LearningStep.step_title.label('step_title')
    ).join(User, ResourceSuggestion.user_id == User.id) \
        .join(LearningStep, ResourceSuggestion.step_id == LearningStep.id) \
        .filter(ResourceSuggestion.status == 'pending').all()

    # The query returns tuples, so we need to map them for the template
    suggestions_list = []
    for suggestion, username, step_title in suggestions:
        suggestion.suggester_username = username
        suggestion.step_title = step_title
        suggestions_list.append(suggestion)

    return render_template('admin_suggestion.html', suggestions=suggestions_list)


@app.route('/admin/approve_suggestion/<int:suggestion_id>')
def approve_suggestion(suggestion_id):
    if not is_admin():
        flash("You do not have permission to perform this action.", "danger")
        return redirect(url_for('home'))

    suggestion = ResourceSuggestion.query.get_or_404(suggestion_id)

    # Create a new, permanent resource from the suggestion
    new_resource = Resource(
        resource_title=suggestion.title,
        url=suggestion.url,
        resource_type=suggestion.resource_type,
        step_id=suggestion.step_id
    )
    db.session.add(new_resource)

    # Update the suggestion's status
    suggestion.status = 'approved'
    db.session.commit()

    flash("Suggestion approved and added as a resource.", "success")
    return redirect(url_for('admin_suggestions'))


@app.route('/admin/reject_suggestion/<int:suggestion_id>')
def reject_suggestion(suggestion_id):
    if not is_admin():
        flash("You do not have permission to perform this action.", "danger")
        return redirect(url_for('home'))

    suggestion = ResourceSuggestion.query.get_or_404(suggestion_id)
    suggestion.status = 'rejected'
    db.session.commit()

    flash("Suggestion has been rejected.", "info")
    return redirect(url_for('admin_suggestions'))


@app.route('/path/<int:path_id>', endpoint='view_specific_path')
@app.route('/')
def home(path_id=None):
    # --- 1. User and Session Handling ---
    if 'user_id' not in session:
        flash("Please log in to view your dashboard.", "warning")
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    if not user:
        # Handle case where user_id in session is invalid
        session.pop('user_id', None)
        flash("User not found, please log in again.", "warning")
        return redirect(url_for('login'))

    # --- 2. Learning Path Logic ---
    learning_path = None
    if path_id:
        # If a path ID is in the URL, find that specific path.
        # The query also ensures the path belongs to the logged-in user for security.
        learning_path = LearningPath.query.filter_by(id=path_id, user_id=user.id).first_or_404()
    else:
        # If no path ID is in the URL, default to the most recent path.
        learning_path = LearningPath.query.filter_by(user_id=user.id).order_by(
            LearningPath.created_at.desc()).first()

    # --- 3. Data Fetching for the Dashboard ---
    user_notes = {}
    progress_percentage = 0
    user_rated_steps = set()

    # This block runs only if a learning path was found (either specific or recent)
    if learning_path:
        db.session.refresh(learning_path)
        step_ids = [step.id for step in learning_path.learning_steps]

        # Fetch notes and ratings for the steps in the current path
        notes_query = UserNote.query.filter(UserNote.user_id == user.id, UserNote.step_id.in_(step_ids)).all()
        user_notes = {note.step_id: note.content for note in notes_query}
        rated_steps_query = StepRating.query.filter_by(user_id=user.id).all()
        user_rated_steps = {rating.step_id for rating in rated_steps_query}

        # Calculate progress percentage
        total_steps = len(learning_path.learning_steps)
        if total_steps > 0:
            completed_steps = len([s for s in learning_path.learning_steps if s.status == 'complete'])
            progress_percentage = round((completed_steps / total_steps) * 100)

        # Check for associated quizzes and problem sets (optimized)
        topic_ids = {step.topic_id for step in learning_path.learning_steps}
        topics_with_quizzes = {q.topic_id for q in QuizQuestion.query.filter(QuizQuestion.topic_id.in_(topic_ids))}
        topics_with_problems = {p.topic_id for p in ProblemSet.query.filter(ProblemSet.topic_id.in_(topic_ids))}
        for step in learning_path.learning_steps:
            step.has_quiz = step.topic_id in topics_with_quizzes
            step.has_problem_set = step.topic_id in topics_with_problems

    # --- 4. Render the Final Template ---
    # This single render call handles all cases
    return render_template(
        'dashboard.html',
        user=user,
        learning_path=learning_path,
        user_notes=user_notes,
        progress_percentage=progress_percentage,
        is_admin=is_admin(),
        user_rated_steps=user_rated_steps
    )



@app.route("/register", methods=["GET", "POST"])
def register():
    """Handles user registration."""
    if request.method == "POST":
        # Get all data from the form once
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        first_name = request.form.get("first_name")
        last_name = request.form.get("last_name")

        # --- Single, comprehensive validation block ---
        if not all([username, email, password, confirmation, first_name, last_name]):
            flash("All fields are required.", "danger")
            return render_template("register.html")

        if password != confirmation:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            flash("This username is already taken.", "danger")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("This email address is already registered.", "danger")
            return render_template("register.html")
        # --- End of validation ---

        # Create new user if all checks pass
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            first_name=first_name,
            last_name=last_name
        )
        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    # For GET requests, just show the registration page
    return render_template("register.html")


@app.route('/generate_quiz/<string:topic_id>', methods=['POST'])
def generate_quiz(topic_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    topic = Topic.query.get_or_404(topic_id)

    # A simple prompt for the AI
    prompt = (
        f"You are a teacher creating a multiple-choice quiz on the topic: '{topic.title}'. "
        "Create exactly 3 multiple-choice questions. "
        "Your response MUST be a single, raw JSON object containing a key 'quiz' which is a list of objects. "
        "Each object must have these exact keys: 'question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option'. "
        "The value for 'correct_option' must be a single capital letter: 'A', 'B', 'C', or 'D'."
    )

    try:
        ollama_payload = {"model": OLLAMA_MODEL, "prompt": prompt, "format": "json", "stream": False}
        response = requests.post(OLLAMA_API_URL, json=ollama_payload, timeout=60)
        response.raise_for_status()

        ai_response_str = response.json().get('response', '{}').strip()
        quiz_data = json.loads(ai_response_str)

        for q_data in quiz_data.get('quiz', []):
            new_question = QuizQuestion(
                topic_id=topic.id,
                question_text=q_data['question_text'],
                option_a=q_data['option_a'],
                option_b=q_data['option_b'],
                option_c=q_data['option_c'],
                option_d=q_data['option_d'],
                correct_option=q_data['correct_option'].upper()
            )
            db.session.add(new_question)

        db.session.commit()
        return jsonify({'success': True, 'message': 'Quiz generated successfully!'})

    except Exception as e:
        db.session.rollback()
        print(f"Quiz generation error: {e}")
        return jsonify({'success': False, 'message': 'The AI failed to generate a valid quiz.'}), 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


@app.route('/generate_path', methods=['GET', 'POST'])
def generate_path():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        goal_title = request.form.get('goal_title').strip()
        if not goal_title:
            flash('Learning goal cannot be empty!', 'danger')
            return render_template('generate_path.html')

        # --- Enhanced Keyword & Tag Search Logic ---
        search_terms = goal_title.lower().split()
        topic_scores = {}

        for topic_id, topic_data in KNOWLEDGE_GRAPH.items():
            score = 0
            text_to_search = (
                    topic_data.get('title', '').lower() + ' ' +
                    topic_data.get('description', '').lower() + ' ' +
                    ' '.join(topic_data.get('keywords', [])) + ' ' +
                    ' '.join(topic_data.get('tags', []))
            ).lower()

            for term in search_terms:
                if term in text_to_search:
                    score += 1

            if score > 0:
                topic_scores[topic_id] = score

        if not topic_scores:
            flash("Could not find relevant topics. Please try rephrasing.", "warning")
            return redirect(url_for('generate_path'))

        sorted_topics = sorted(topic_scores.items(), key=lambda item: item[1], reverse=True)
        target_ids = {topic_id for topic_id, score in sorted_topics[:5]}




        # --- START OF DEBUGGING SECTION ---
        print("\n--- STARTING DEBUG ---")
        print(f"DEBUG: Initial target topic IDs from search: {target_ids}")

        full_path_ids = set()
        queue = list(target_ids)
        visited_prereqs = set()

        while queue:
            current_id = queue.pop(0)
            if current_id not in full_path_ids:
                full_path_ids.add(current_id)
                topic_info = KNOWLEDGE_GRAPH.get(current_id, {})
                for prereq_id in topic_info.get('prerequisites', []):
                    if prereq_id not in visited_prereqs:
                        queue.append(prereq_id)
                        visited_prereqs.add(prereq_id)

        print(f"DEBUG: Full path IDs after adding prerequisites: {full_path_ids}")

        user_known_ids = set(user.known_topics_ids.split(',')) if user.known_topics_ids else set()
        steps_to_create_ids = list(full_path_ids - user_known_ids)

        print(f"DEBUG: Final list of step IDs to create: {steps_to_create_ids}")

        if not steps_to_create_ids:
            flash("You already know all topics related to this goal!", "info")
            return redirect(url_for('generate_path'))

        all_topics_in_graph = [topic['id'] for topic in KNOWLEDGE_GRAPH.values()]
        ordered_steps_data = sorted(
            Topic.query.filter(Topic.id.in_(steps_to_create_ids)).all(),
            key=lambda t: all_topics_in_graph.index(t.id) if t.id in all_topics_in_graph else float('inf')
        )

        new_path = LearningPath(user_id=user.id, goal_title=goal_title)
        db.session.add(new_path)
        db.session.commit()

        step_counter = 1
        print("\nDEBUG: Now creating steps and adding resources...")
        for topic in ordered_steps_data:
            print(f"\n  Processing Topic ID: {topic.id} ({topic.title})")

            step = LearningStep(path_id=new_path.id, topic_id=topic.id, step_title=topic.title,
                                description=topic.description, status='pending', step_number=step_counter)
            db.session.add(step)
            db.session.flush()

            topic_info = KNOWLEDGE_GRAPH.get(topic.id, {})
            resources = topic_info.get('default_resources', [])

            if not resources:
                print(f"    -> No 'default_resources' found for this topic in knowledge_graph.json.")
            else:
                print(f"    -> Found {len(resources)} resources. Adding them now...")
                for res_data in resources:
                    # Use the correct keys that match your data file ('resource_title', 'resource_type')
                    # Also, provide a more user-friendly default value like "Untitled"
                    title = res_data.get('resource_title', 'Untitled Resource')
                    r_type = res_data.get('resource_type', 'article')

                    print(f"      - Adding '{title}'")
                    db.session.add(Resource(
                        learning_step=step,
                        resource_title=title,
                        url=res_data['url'],
                        resource_type=r_type
                    ))

            step_counter += 1

        db.session.commit()
        print("--- END OF DEBUG ---")

        flash(f'Your new learning path "{new_path.goal_title}" has been created!', 'success')
        return redirect(url_for('home'))




    # For GET requests
    known_ids = user.known_topics_ids.split(',') if user.known_topics_ids else []
    known_topics_list = Topic.query.filter(Topic.id.in_(known_ids)).all() if known_ids else []
    prefill_known_topics = ", ".join([t.title for t in known_topics_list])
    return render_template('generate_path.html', prefill_known_topics=prefill_known_topics)


@app.route('/update_knowledge', methods=['GET', 'POST'])
def update_knowledge():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        known_topics_str = request.form.get('known_topics', '')
        newly_submitted_known_topic_ids = set()
        if known_topics_str:
            for topic_title in known_topics_str.split(','):
                topic = Topic.query.filter(Topic.title.ilike(topic_title.strip())).first()
                if topic: newly_submitted_known_topic_ids.add(topic.id)
        user.known_topics_ids = ",".join(sorted(list(newly_submitted_known_topic_ids)))
        db.session.commit()
        flash('Your knowledge profile has been updated!', 'success')
        return redirect(url_for('profile'))

    known_ids = user.known_topics_ids.split(',') if user.known_topics_ids else []
    known_topics_list = Topic.query.filter(Topic.id.in_(known_ids)).all() if known_ids else []
    prefill_known_topics = ", ".join([t.title for t in known_topics_list])
    return render_template('update_knowledge.html', prefill_known_topics=prefill_known_topics)


@app.route('/suggest_resource/<int:step_id>', methods=['GET', 'POST'])
def suggest_resource(step_id):
    if 'user_id' not in session:
        flash('Please log in to suggest a resource.', 'warning')
        return redirect(url_for('login'))

    step = LearningStep.query.get_or_404(step_id)
    # Security check: ensure the step belongs to the current user's path
    if step.learning_path.user_id != session['user_id']:
        flash('You can only suggest resources for your own learning path.', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form.get('title')
        url = request.form.get('url')
        resource_type = request.form.get('resource_type')

        if not title or not url:
            flash('Title and URL are required.', 'danger')
            return render_template('suggest_resource.html', step=step)

        suggestion = ResourceSuggestion(
            user_id=session['user_id'],
            step_id=step.id,
            title=title,
            url=url,
            resource_type=resource_type
        )
        db.session.add(suggestion)
        db.session.commit()
        flash('Thank you! Your suggestion has been submitted for review.', 'success')
        return redirect(url_for('home'))

    return render_template('suggest_resource.html', step=step)


@app.route('/debug-data')
def debug_data():
    # Fetch all topics and all resources from the database
    all_topics = Topic.query.all()
    all_resources = Resource.query.all()
    return render_template('debug.html', topics=all_topics, resources=all_resources)


@app.route('/profile')
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    user_learning_paths = LearningPath.query.filter_by(user_id=user.id).order_by(LearningPath.created_at.desc()).all()
    known_ids = user.known_topics_ids.split(',') if user.known_topics_ids else []
    known_topics_list = Topic.query.filter(Topic.id.in_(known_ids)).all() if known_ids else []
    return render_template('profile.html', user=user, learning_paths=user_learning_paths,
                           known_topics_list=[t.title for t in known_topics_list])


@app.route('/ask_local_ai', methods=['POST'])
def ask_local_ai():
    if 'user_id' not in session:
        return Response("Unauthorized", status=401)

    data = request.get_json()
    user_message = data.get('message')
    context = data.get('context', 'a general topic')
    step_id = data.get('stepId')
    user_id = session['user_id']

    if not all([user_message, context, step_id]):
        return Response("Missing required data.", status=400)

    # Save the user's message first
    try:
        user_chat_message = ChatMessage(content=user_message, role='user', user_id=user_id, step_id=step_id)
        db.session.add(user_chat_message)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error saving user message: {e}")

    # This generator function will stream the AI's response
    def generate_and_save(uid, sid):
        full_ai_response_text = []
        try:
            # This new prompt tells the AI to both explain AND ask questions.
            full_prompt = (
                f"You are a helpful tutor teaching the topic of '{context}'. "
                f"Your goal is to help the student learn. First, provide a brief, clear explanation related to their question. "
                f"Then, end your response with a single, guiding question to make them think more deeply. "
                f"You must ONLY answer questions related to '{context}'. If the user asks about anything else, politely refuse. "
                f"The student's question is: {user_message}"
            )

            ollama_payload = {
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": True
            }
            with requests.post(OLLAMA_API_URL, json=ollama_payload, stream=True) as r:
                # ...

                for chunk in r.iter_lines():
                    if chunk:
                        json_chunk = json.loads(chunk)
                        token = json_chunk.get("response", "")
                        full_ai_response_text.append(token)
                        yield token

                        if json_chunk.get("done"):
                            break


            # Once streaming is finished, save the complete response inside a new app context.
            final_text = "".join(full_ai_response_text)
            with app.app_context():
                ai_chat_message = ChatMessage(content=final_text, role='ai', user_id=uid, step_id=sid)
                db.session.add(ai_chat_message)
                db.session.commit()

        except Exception as e:
            print(f"Streaming AI error: {e}")
            yield f" An error occurred: {e}"

    return Response(generate_and_save(user_id, step_id), mimetype='text/plain')


@app.route('/quiz/<string:topic_id>', methods=['GET', 'POST'])
def quiz(topic_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    questions = QuizQuestion.query.filter_by(topic_id=topic_id).all()
    if not questions:
        flash("No quiz found for this topic.", 'info')
        return redirect(url_for('home'))
    if request.method == 'POST':
        return redirect(url_for('home'))
    return render_template('quiz.html', questions=questions, topic_id=topic_id)


@app.route('/problem_set/<string:topic_id>')
def problem_set(topic_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    problems = ProblemSet.query.filter_by(topic_id=topic_id).all()
    if not problems:
        flash("No problem sets found for this topic.", 'info')
        return redirect(url_for('home'))
    return render_template('problem_set.html', problems=problems, topic_id=topic_id)


@app.route('/mark_problem_step_complete/<int:problem_id>', methods=['POST'])
def mark_problem_step_complete(problem_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    problem = ProblemSet.query.get_or_404(problem_id)
    user = User.query.get(session['user_id'])
    learning_path = LearningPath.query.filter_by(user_id=user.id).order_by(LearningPath.created_at.desc()).first()
    if learning_path:
        target_step = LearningStep.query.filter_by(path_id=learning_path.id, topic_id=problem.topic_id).first()
        if target_step and target_step.status == 'pending':
            target_step.status = 'complete'
            grant_points_and_badges(user, 10)
            flash(f"'{target_step.step_title}' marked as complete!", "success")
    return redirect(url_for('home'))


@app.route('/get_chat_history/<int:step_id>')
def get_chat_history(step_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    messages = ChatMessage.query.filter_by(
        user_id=session['user_id'],
        step_id=step_id
    ).order_by(ChatMessage.created_at).all()

    history = []
    for msg in messages:
        # Convert AI markdown to HTML for display
        content = mistune.html(msg.content) if msg.role == 'ai' else msg.content
        history.append({'role': msg.role, 'content': content})

    return jsonify({'history': history})


@app.route('/update_step_status/<int:step_id>', methods=['POST'])
def update_step_status(step_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    user_id = session['user_id']
    step = LearningStep.query.get(step_id)

    if not step:
        return jsonify({'success': False, 'message': 'Step not found'}), 404

    # Security check to ensure the step belongs to the user
    if step.learning_path.user_id != user_id:
        return jsonify({'success': False, 'message': 'Forbidden'}), 403

    # Only perform actions if the step is currently pending
    if step.status == 'pending':
        step.status = 'complete'
        try:
            user = User.query.get(user_id)
            if user:
                # Grant points and check for new badges
                grant_points_and_badges(user, 10)

                # Find the associated topic to generate flashcards for
                topic = Topic.query.get(step.topic_id)
                if topic:
                    # This new call creates the review items for the SRS
                    create_review_items_for_topic(user, topic)

            # Commit all changes (status, points, badges, new review items)
            db.session.commit()

            # Expire the path to ensure the progress bar updates correctly
            db.session.expire(step.learning_path)

            return jsonify({'success': True, 'message': 'Step marked as complete'})
        except Exception as e:
            db.session.rollback()
            print(f"Error in update_step_status: {e}")
            return jsonify({'success': False, 'message': f'Database error: {e}'}), 500
    else:
        # If the step was already complete, do nothing but report success
        return jsonify({'success': True, 'message': 'Step already complete'})


@app.route('/portfolio/<string:username>')
def portfolio(username):
    # Find the user by their username, or show a 404 error if not found
    user = User.query.filter_by(username=username).first_or_404()

    # Fetch all project submissions for this user, ordered by most recent
    projects = ProjectSubmission.query.filter_by(user_id=user.id)\
                                      .order_by(ProjectSubmission.completed_at.desc()).all()

    return render_template('portfolio.html', user=user, projects=projects)


@app.route('/review')
def review():
    if 'user_id' not in session:
        flash('You must be logged in to review.', 'warning')
        return redirect(url_for('login'))

    # Find all review items that are due today or earlier
    due_items = ReviewItem.query.filter(
        ReviewItem.user_id == session['user_id'],
        ReviewItem.next_review_at <= datetime.datetime.utcnow()
    ).order_by(ReviewItem.next_review_at).all()

    return render_template('review.html', review_items=due_items)


@app.route('/update_review_item/<int:item_id>', methods=['POST'])
def update_review_item(item_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    item = ReviewItem.query.get_or_404(item_id)
    if item.user.id != session['user_id']:
        return jsonify({'success': False, 'message': 'Forbidden'}), 403

    grade = request.json.get('grade')

    # Simple Spaced Repetition (SRS) Algorithm
    if grade == 'good':
        item.interval *= 2 # Double the interval
    elif grade == 'hard':
        item.interval = 1 # Reset the interval
    # If grade is 'easy', we can make the interval even longer
    elif grade == 'easy':
        item.interval *= 4

    item.next_review_at = datetime.datetime.utcnow() + datetime.timedelta(days=item.interval)
    db.session.commit()

    return jsonify({'success': True})


@app.route('/clear_chat_history/<int:step_id>', methods=['POST'])
def clear_chat_history(step_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        # Find and delete all messages for this user and this step
        ChatMessage.query.filter_by(
            user_id=session['user_id'],
            step_id=step_id
        ).delete()

        db.session.commit()
        return jsonify({'success': True, 'message': 'Chat history cleared.'})
    except Exception as e:
        db.session.rollback()
        print(f"Error clearing chat history: {e}")
        return jsonify({'success': False, 'message': 'An error occurred.'}), 500


@app.route('/resource_finder', methods=['GET', 'POST'])
def resource_finder():
    if 'user_id' not in session:
        flash('You must be logged in to use this feature.', 'warning')
        return redirect(url_for('login'))

    found_topics = []
    last_query = ""

    if request.method == 'POST':
        user_query = request.form.get('user_query')
        last_query = user_query

        if user_query:
            # Split the user's query into individual words
            search_terms = user_query.lower().split()

            # Build a dynamic search query
            search_conditions = []
            for term in search_terms:
                search_conditions.append(Topic.title.ilike(f'%{term}%'))
                search_conditions.append(Topic.description.ilike(f'%{term}%'))
                search_conditions.append(Topic.keywords.ilike(f'%{term}%'))

            # Find all topics that match any of the keywords
            if search_conditions:
                found_topics = Topic.query.filter(or_(*search_conditions)).all()

        if not found_topics:
            flash("No matching topics were found for your query.", "info")

    return render_template('resource_finder.html',
                           found_topics=found_topics,
                           last_query=last_query)


@app.route('/submit_project/<int:path_id>', methods=['POST'])
def submit_project(path_id):
    if 'user_id' not in session:
        flash("You must be logged in to submit a project.", "warning")
        return redirect(url_for('login'))

    learning_path = LearningPath.query.get_or_404(path_id)

    # Security check to ensure the path belongs to the current user
    if learning_path.user_id != session['user_id']:
        flash("You can only submit projects for your own learning paths.", "danger")
        return redirect(url_for('home'))

    # Check if a project has already been submitted for this path
    if learning_path.submission:
        flash("A project has already been submitted for this learning path.", "warning")
        return redirect(url_for('home'))

    title = request.form.get('project_title')
    url = request.form.get('project_url')
    description = request.form.get('project_description')

    if not title or not url:
        flash("Project Title and Project URL are required fields.", "danger")
        return redirect(url_for('home'))

    try:
        # Generate a unique ID for the certificate
        cert_id = str(uuid.uuid4())

        submission = ProjectSubmission(
            project_title=title,
            project_url=url,
            project_description=description,
            user_id=session['user_id'],
            learning_path_id=path_id,
            certificate_id=cert_id
        )
        db.session.add(submission)
        db.session.commit()

        flash("Congratulations! Your project has been added to your portfolio.", "success")
        # Redirect the user directly to their new certificate
        return redirect(url_for('view_certificate', certificate_id=cert_id))

    except Exception as e:
        db.session.rollback()
        print(f"Error submitting project: {e}")
        flash("An error occurred while submitting your project.", "danger")
        return redirect(url_for('home'))


@app.route('/save_note', methods=['POST'])
def save_note():
    # 1. Security: Ensure the user is logged in
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'User not logged in'}), 401

    data = request.get_json()
    step_id = data.get('stepId')
    raw_content = data.get('content')
    user_id = session['user_id']

    if not step_id:
        return jsonify({'success': False, 'message': 'Missing step ID'}), 400

    # 2. Sanitize user input to prevent XSS attacks
    allowed_tags = ['b', 'i', 'u', 'p', 'br', 'div', 'strong', 'em', 'ol', 'ul', 'li', 'span']

    # We've added a dictionary to specify which attributes are allowed on which tags
    allowed_attributes = {
        'span': ['style']  # This allows the 'style' attribute ONLY on 'span' tags
    }

    # The bleach.clean call is updated to use the new rules
    cleaned_content = bleach.clean(
        raw_content,
        tags=allowed_tags,
        attributes=allowed_attributes
    )
    # --- END OF CORRECTION ---

    try:
        # 3. "Upsert" logic: Update the note if it exists, or insert it if it's new
        note = UserNote.query.filter_by(user_id=user_id, step_id=step_id).first()

        if note:
            # If note exists, update its content
            note.content = cleaned_content
        else:
            # If note doesn't exist, create a new one
            note = UserNote(user_id=user_id, step_id=step_id, content=cleaned_content)
            db.session.add(note)

        db.session.commit()

        # 4. Return a success response to the JavaScript fetch call
        return jsonify({'success': True, 'message': 'Note saved successfully.'})

    except Exception as e:
        db.session.rollback()
        print(f"Error saving note: {e}")
        return jsonify({'success': False, 'message': 'A database error occurred.'}), 500


@app.route('/export_notes/<int:path_id>')
def export_notes(path_id):
    """Exports all notes for a specific learning path as a downloadable PDF."""
    if 'user_id' not in session:
        flash("Please log in to export your notes.", "warning")
        return redirect(url_for('login'))

    user = User.query.get_or_404(session['user_id'])
    learning_path = LearningPath.query.filter_by(id=path_id, user_id=user.id).first_or_404()

    # This single, efficient query gets all notes and their corresponding step details.
    notes_query = db.session.query(UserNote, LearningStep)\
        .join(LearningStep, UserNote.step_id == LearningStep.id)\
        .filter(UserNote.user_id == user.id, LearningStep.path_id == path_id)\
        .order_by(LearningStep.step_number)\
        .all()

    # Use render_template to generate the HTML from a dedicated file.
    html_content = render_template(
        'export_template.html',
        learning_path=learning_path,
        user=user,
        notes_query=notes_query,
        current_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    )

    # The PDF generation part remains the same
    try:
        html_doc = HTML(string=html_content)
        pdf_bytes = html_doc.write_pdf()
    except Exception as e:
        print(f"Error generating PDF with WeasyPrint: {e}")
        flash("An error occurred while generating the PDF.", "danger")
        return redirect(url_for('home'))

    sanitized_goal_title = re.sub(r'[^\w\s-]', '', learning_path.goal_title).strip()
    filename = f"notes_{sanitized_goal_title.replace(' ', '_').lower()}.pdf"

    response = Response(pdf_bytes, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"

    return response




# APP RUNNER
if __name__ == '__main__':
    app.run(debug=True)

