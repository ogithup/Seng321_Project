import os
from datetime import datetime 
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import docx 
from functools import wraps
import os

# Project internal imports
from config import Config
from models.database import db
from models.entities import User, Submission, Grade, LearningActivity, LearningGoal, Quiz 
from services.ai_service import AIService
from services.ocr_service import OCRService

def create_app():
    app = Flask(__name__)
    UPLOAD_FOLDER = 'static/profile_pics'
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.config.from_object(Config)

    # Initialize Database
    db.init_app(app)

    # Login Manager Setup
    login_manager = LoginManager()
    login_manager.login_view = 'login' 
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- GLOBAL USER INJECTION ---
    @app.context_processor
    def inject_user():
        return dict(user=current_user)

    # Configure Upload Folder
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/uploads')
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    os.makedirs(UPLOAD_FOLDER, exist_ok=True) 

    # Create Database Tables
    with app.app_context():
        db.create_all()

    # --- AUTHENTICATION CHECK & CACHE CONTROL ---
    @app.before_request
    def check_user_auth():
        public_routes = ['login', 'register', 'static', 'privacy', 'terms']
        if not current_user.is_authenticated and request.endpoint not in public_routes:
            return redirect(url_for('login'))
        
    @app.after_request
    def add_header(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
    
    # Role Based Access Decorator
    def role_required(role):
        def wrapper(fn):
            @wraps(fn)
            @login_required
            def decorated_view(*args, **kwargs):
                if current_user.role != role:
                    flash(f"Access Denied: Only {role}s are authorized.", "danger")
                    return redirect(url_for('dashboard'))
                return fn(*args, **kwargs)
            return decorated_view
        return wrapper

    # --- AUTH ROUTES ---
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))

    @app.route('/register', methods=['POST'])
    def register():
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'Student') 
        if User.query.filter_by(email=email).first():
            flash("Email already exists!", "danger")
            return redirect(url_for('login'))
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, email=email, password=hashed_pw, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful!", "success")
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated: return redirect(url_for('dashboard'))
        if request.method == 'POST':
            user = User.query.filter_by(email=request.form.get('email')).first()
            if user and check_password_hash(user.password, request.form.get('password')):
                login_user(user)
                return redirect(url_for('dashboard'))
            flash("Invalid credentials.", "danger")
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        if current_user.role == 'Instructor':
            return redirect(url_for('instructor_dashboard'))
        
        from datetime import timedelta
        
        # Get all submissions
        submissions = Submission.query.filter_by(student_id=current_user.id).order_by(Submission.created_at.asc()).all()
        
        # Calculate Speaking Score (average of pronunciation_score and fluency_score)
        speaking_subs = [s for s in submissions if s.submission_type == 'SPEAKING' and s.grade]
        speaking_score = 0.0
        if speaking_subs:
            scores = []
            for sub in speaking_subs:
                if sub.grade.pronunciation_score and sub.grade.fluency_score:
                    scores.append((sub.grade.pronunciation_score + sub.grade.fluency_score) / 2)
            speaking_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        
        # Calculate Writing Score (average of writing submissions)
        writing_subs = [s for s in submissions if s.submission_type == 'WRITING' and s.grade]
        writing_score = round(sum(s.grade.score for s in writing_subs) / len(writing_subs), 1) if writing_subs else 0.0
        
        # Calculate Quiz Progress
        all_quizzes = Quiz.query.filter_by(user_id=current_user.id).all()
        completed_quizzes = len(all_quizzes)
        quiz_progress = completed_quizzes  # Can be enhanced with total available quizzes
        
        # Calculate Current Streak (consecutive days with submissions)
        current_streak = 0
        if submissions:
            # Get unique submission dates
            submission_dates = set()
            for sub in submissions:
                submission_dates.add(sub.created_at.date())
            
            # Calculate streak backwards from today
            today = datetime.utcnow().date()
            check_date = today
            while check_date in submission_dates:
                current_streak += 1
                check_date -= timedelta(days=1)
        
        # Calculate Weekly Goal Progress
        today = datetime.utcnow().date()
        week_start = today - timedelta(days=today.weekday())  # Monday of current week
        weekly_submissions = [s for s in submissions if s.created_at.date() >= week_start]
        weekly_goal_current = len(weekly_submissions)
        weekly_goal_target = 5  # Default weekly goal
        weekly_goal_percentage = min(100, int((weekly_goal_current / weekly_goal_target) * 100)) if weekly_goal_target > 0 else 0
        weekly_goal_remaining = max(0, weekly_goal_target - weekly_goal_current)
        
        # Get recent submissions for the chart
        recent_submissions = submissions[-10:] if len(submissions) > 10 else submissions
        
        # Calculate Handwritten Score
        handwritten_subs = [s for s in submissions if s.submission_type == 'HANDWRITTEN' and s.grade]
        
        # Prepare multi-line chart data: Speaking, Writing, Quiz, Handwritten scores by date
        from collections import defaultdict
        chart_data = {
            'dates': [],
            'speaking_scores': [],
            'writing_scores': [],
            'quiz_scores': [],
            'handwritten_scores': []
        }
        
        # Get Handwritten submissions
        handwritten_subs = [s for s in submissions if s.submission_type == 'HANDWRITTEN' and s.grade]
        
        # Collect all dates from submissions and quizzes
        all_dates = set()
        
        # Speaking submissions with dates
        for sub in speaking_subs:
            if sub.grade and sub.grade.pronunciation_score is not None and sub.grade.fluency_score is not None:
                date_key = sub.created_at.date()
                all_dates.add(date_key)
        
        # Writing submissions with dates
        for sub in writing_subs:
            if sub.grade and sub.grade.score is not None:
                date_key = sub.created_at.date()
                all_dates.add(date_key)
        
        # Handwritten submissions with dates
        for sub in handwritten_subs:
            if sub.grade and sub.grade.score is not None:
                date_key = sub.created_at.date()
                all_dates.add(date_key)
        
        # Quiz submissions with dates
        for quiz in all_quizzes:
            if quiz.date_taken and quiz.score is not None:
                date_key = quiz.date_taken.date() if isinstance(quiz.date_taken, datetime) else quiz.date_taken
                all_dates.add(date_key)
        
        # Sort dates
        sorted_dates = sorted(all_dates)
        
        # Create date-indexed dictionaries
        speaking_by_date = {}
        writing_by_date = {}
        handwritten_by_date = {}
        quiz_by_date = {}
        
        for sub in speaking_subs:
            if sub.grade and sub.grade.pronunciation_score is not None and sub.grade.fluency_score is not None:
                date_key = sub.created_at.date()
                score = (sub.grade.pronunciation_score + sub.grade.fluency_score) / 2
                if date_key not in speaking_by_date:
                    speaking_by_date[date_key] = []
                speaking_by_date[date_key].append(score)
        
        for sub in writing_subs:
            if sub.grade and sub.grade.score is not None:
                date_key = sub.created_at.date()
                if date_key not in writing_by_date:
                    writing_by_date[date_key] = []
                writing_by_date[date_key].append(sub.grade.score)
        
        for sub in handwritten_subs:
            if sub.grade and sub.grade.score is not None:
                date_key = sub.created_at.date()
                if date_key not in handwritten_by_date:
                    handwritten_by_date[date_key] = []
                handwritten_by_date[date_key].append(sub.grade.score)
        
        for quiz in all_quizzes:
            if quiz.date_taken and quiz.score is not None:
                date_key = quiz.date_taken.date() if isinstance(quiz.date_taken, datetime) else quiz.date_taken
                if date_key not in quiz_by_date:
                    quiz_by_date[date_key] = []
                quiz_by_date[date_key].append(quiz.score)
        
        # Average scores per date and build chart data
        for date in sorted_dates:
            chart_data['dates'].append(date.strftime('%d %b'))
            
            # Speaking: average if multiple submissions on same date
            if date in speaking_by_date:
                chart_data['speaking_scores'].append(round(sum(speaking_by_date[date]) / len(speaking_by_date[date]), 1))
            else:
                chart_data['speaking_scores'].append(0)  # Use 0 instead of None for better chart display
            
            # Writing: average if multiple submissions on same date
            if date in writing_by_date:
                chart_data['writing_scores'].append(round(sum(writing_by_date[date]) / len(writing_by_date[date]), 1))
            else:
                chart_data['writing_scores'].append(0)  # Use 0 instead of None
            
            # Handwritten: average if multiple submissions on same date
            if date in handwritten_by_date:
                chart_data['handwritten_scores'].append(round(sum(handwritten_by_date[date]) / len(handwritten_by_date[date]), 1))
            else:
                chart_data['handwritten_scores'].append(0)  # Use 0 instead of None
            
            # Quiz: average if multiple quizzes on same date
            if date in quiz_by_date:
                chart_data['quiz_scores'].append(round(sum(quiz_by_date[date]) / len(quiz_by_date[date]), 1))
            else:
                chart_data['quiz_scores'].append(0)  # Use 0 instead of None
        
        # Calculate Handwritten Score for insights
        handwritten_score = 0.0
        if handwritten_subs:
            handwritten_score = round(sum(s.grade.score for s in handwritten_subs) / len(handwritten_subs), 1)
        
        # Calculate Quiz Score for insights
        quiz_score = 0.0
        if all_quizzes:
            quiz_scores_list = [q.score for q in all_quizzes if q.score is not None]
            quiz_score = round(sum(quiz_scores_list) / len(quiz_scores_list), 1) if quiz_scores_list else 0.0
        
        # Determine AI Performance Insights (Strongest and Weakest areas)
        area_scores = {
            'Speaking': speaking_score,
            'Writing': writing_score,
            'Quiz': quiz_score,
            'Handwritten': handwritten_score
        }
        
        # Filter out zero scores for comparison
        non_zero_scores = {k: v for k, v in area_scores.items() if v > 0}
        
        if non_zero_scores:
            strongest_area = max(non_zero_scores, key=non_zero_scores.get)
            weakest_area = min(non_zero_scores, key=non_zero_scores.get)
            strongest_score = non_zero_scores[strongest_area]
            weakest_score = non_zero_scores[weakest_area]
        else:
            # If all scores are zero, show default values
            strongest_area = 'Speaking'
            weakest_area = 'Handwritten'
            strongest_score = 0.0
            weakest_score = 0.0
        
        # Determine Recommended Next Step
        recommended_next = "Start Your First Activity"
        recommended_link = "/assignments"
        if not speaking_subs:
            recommended_next = "Improve Your Speaking"
            recommended_link = "/speaking"
        elif not writing_subs:
            recommended_next = "Improve Your Writing"
            recommended_link = "/submit/writing"
        elif speaking_score < 70:
            recommended_next = "Improve Your Speaking"
            recommended_link = "/speaking"
        elif writing_score < 70:
            recommended_next = "Improve Your Writing"
            recommended_link = "/submit/writing"
        elif completed_quizzes == 0:
            recommended_next = "Take a Quiz"
            recommended_link = "/quizzes"
        
        # Get latest graded submission for recommendations
        latest_graded = Submission.query.filter_by(student_id=current_user.id).join(Grade).order_by(Submission.created_at.desc()).first()
        
        # Get user goals
        user_goals = LearningGoal.query.filter_by(user_id=current_user.id).limit(2).all()
        
        # Calculate pending tasks (all activities - in a real app, these would be filtered by student assignments)
        # For now, we'll count activities with future due dates
        pending_activities = LearningActivity.query.filter(
            LearningActivity.due_date >= datetime.utcnow()
        ).order_by(LearningActivity.due_date.asc()).all()
        pending_count = len(pending_activities)
        
        # Calculate total submissions
        total_submissions = len(submissions)
        
        # Calculate average score across all graded submissions
        graded_subs = [s for s in submissions if s.grade]
        avg_score = round(sum(s.grade.score for s in graded_subs) / len(graded_subs), 1) if graded_subs else 0.0
        
        return render_template('dashboard.html', 
                               submissions=submissions,
                               recent_submissions=recent_submissions,
                               speaking_score=speaking_score,
                               writing_score=writing_score,
                               quiz_progress=quiz_progress,
                               current_streak=current_streak,
                               weekly_goal_current=weekly_goal_current,
                               weekly_goal_target=weekly_goal_target,
                               weekly_goal_percentage=weekly_goal_percentage,
                               weekly_goal_remaining=weekly_goal_remaining,
                               recommended_next=recommended_next,
                               recommended_link=recommended_link,
                               latest_graded=latest_graded,
                               goals=user_goals,
                               speaking_subs=speaking_subs,
                               writing_subs=writing_subs,
                               has_chart_data=len(recent_submissions) > 0,
                               chart_data=chart_data,
                               pending_count=pending_count,
                               total_submissions=total_submissions,
                               average_score=avg_score,
                               strongest_area=strongest_area,
                               strongest_score=strongest_score,
                               weakest_area=weakest_area,
                               weakest_score=weakest_score)

    @app.route('/assignments')
    @login_required
    def view_assignments():
        activities = LearningActivity.query.order_by(LearningActivity.due_date.asc()).all()
        now = datetime.utcnow()
        
        # Calculate status counts
        all_count = len(activities)
        pending_count = len([a for a in activities if a.due_date and a.due_date >= now])
        completed_count = len([a for a in activities if a.due_date and a.due_date < now])
        
        return render_template('assignments.html', 
                               activities=activities,
                               all_count=all_count,
                               pending_count=pending_count,
                               completed_count=completed_count,
                               now=now)

    @app.route('/speaking')
    @login_required
    def speaking():
        # Get speaking submissions
        submissions = Submission.query.filter_by(student_id=current_user.id, submission_type='SPEAKING').all()
        speaking_subs = [s for s in submissions if s.grade]
        
        # Calculate average score
        avg_score = 0.0
        if speaking_subs:
            scores = []
            for sub in speaking_subs:
                if sub.grade.pronunciation_score and sub.grade.fluency_score:
                    scores.append((sub.grade.pronunciation_score + sub.grade.fluency_score) / 2)
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
        
        # Get last practice date
        last_practice = None
        if speaking_subs:
            last_sub = max(speaking_subs, key=lambda x: x.created_at)
            last_practice = last_sub.created_at.strftime('%b %d') if last_sub.created_at else None
        
        total_recordings = len(speaking_subs)
        
        return render_template('speaking.html', 
                               avg_score=avg_score,
                               last_practice=last_practice,
                               total_recordings=total_recordings,
                               analysis_results=None)

    @app.route('/quizzes')
    @login_required
    def quizzes():
        user_quizzes = Quiz.query.filter_by(user_id=current_user.id).all()
        return render_template('quizzes.html', quizzes=user_quizzes)
    
    @app.route('/profile')
    @login_required
    def profile():
       return render_template('profile.html', user=current_user) 
      
    # --- UPDATE USER BIOGRAPHY ---
    @app.route('/update_bio', methods=['POST'])
    @login_required
    def update_bio():
        # Get the bio content from the form
        current_user.bio = request.form.get('new_bio')
        try:
            # Save the changes to the database
            db.session.commit()
            flash("Bio updated successfully!", "success")
        except Exception:
            # Rollback in case of database error
            db.session.rollback()
            flash("An error occurred while updating bio.", "danger")
        return redirect(url_for('profile'))

    # --- UPDATE PERSONAL INFORMATION ---
    @app.route('/update_personal_info', methods=['POST'])
    @login_required
    def update_personal_info():
        current_user.university = request.form.get('university')
        current_user.grade = request.form.get('grade')
        current_user.teacher = request.form.get('teacher')
        current_user.phone = request.form.get('phone')
        
        try:
            db.session.commit()
            flash("Personal information updated successfully!", "success")
        except Exception:
            db.session.rollback()
            flash("An error occurred during update.", "danger")
        return redirect(url_for('profile'))
    @app.route('/change_password', methods=['POST'])
    @login_required
    def change_password():
        current_pw = request.form.get('current_password')
        new_pw = request.form.get('new_password')
        confirm_pw = request.form.get('confirm_password')

        # 1. Verify if the current password is correct
        if not check_password_hash(current_user.password, current_pw):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for('settings'))

        # 2. Check if the two new passwords match
        if new_pw != confirm_pw:
            flash("New passwords do not match.", "danger")
            return redirect(url_for('settings'))

        # 3. Hash the new password and update the database
        try:
            current_user.password = generate_password_hash(new_pw, method='pbkdf2:sha256')
            db.session.commit()
            flash("Password changed successfully!", "success")
        except Exception:
            db.session.rollback()
            flash("An error occurred while updating the password.", "danger")

        return redirect(url_for('settings'))

    # --- SETTINGS: UPDATE AI PREFERENCES ---
    @app.route('/update_ai_settings', methods=['POST'])
    @login_required
    def update_ai_settings():
        # Retrieve data from the settings form
        ai_tone = request.form.get('ai_tone')
        ai_speed = request.form.get('ai_speed')
        # Checkbox: returns True if checked, False if not
        ai_reports = 'weekly_report' in request.form 
        
        try:
            # Update user preferences in the database
            current_user.ai_tone = ai_tone
            current_user.ai_speed = float(ai_speed) if ai_speed else 1.0
            current_user.ai_reports = ai_reports
            
            db.session.commit()
            flash("AI Preferences saved successfully!", "success")
        except Exception:
            db.session.rollback()
            flash("Failed to save AI settings.", "danger")
            
        return redirect(url_for('settings'))
      
    @app.route('/goals', methods=['GET', 'POST'])
    @login_required
    def goals():
        if request.method == 'POST':
            # Handle goal creation
            goal_name = request.form.get('goal_name')
            target_value = request.form.get('target_value', type=int)
            current_value = request.form.get('current_value', type=int, default=0)
            category = request.form.get('category', 'General')  # Category for future use
            
            if goal_name and target_value:
                new_goal = LearningGoal(
                    user_id=current_user.id,
                    goal_name=goal_name,
                    target_value=target_value,
                    current_value=current_value
                )
                db.session.add(new_goal)
                db.session.commit()
                
                # Return JSON for AJAX requests
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': True, 'message': 'Goal added successfully!'}), 200
                
                flash('Goal added successfully!', 'success')
                return redirect(url_for('goals'))
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'message': 'Please fill in all required fields.'}), 400
                
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('goals'))
        
        # GET request - display goals
        user_goals = LearningGoal.query.filter_by(user_id=current_user.id).all()
        return render_template('goals.html', goals=user_goals)

    @app.route('/delete-goal/<int:goal_id>', methods=['POST'])
    @login_required
    def delete_goal(goal_id):
        goal = LearningGoal.query.get_or_404(goal_id)
        
        # Ensure user can only delete their own goals
        if goal.user_id != current_user.id:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Permission denied'}), 403
            flash('You do not have permission to delete this goal.', 'error')
            return redirect(url_for('goals'))
        
        try:
            db.session.delete(goal)
            db.session.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': 'Goal deleted successfully!'}), 200
            
            flash('Goal deleted successfully!', 'success')
            return redirect(url_for('goals'))
        except Exception as e:
            db.session.rollback()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': str(e)}), 500
            flash('An error occurred while deleting the goal.', 'error')
            return redirect(url_for('goals'))
    
    @app.route('/settings')
    @login_required
    def settings():
        return render_template('settings.html')
    @app.route('/export')
    @login_required
    def export_data():
        flash("Performance report exported successfully!", "success")
        return redirect(url_for('dashboard'))

    # ---  INSTRUCTOR DASHBOARD ---

    @app.route('/instructor/dashboard')
    @role_required('Instructor')
    def instructor_dashboard():
        from datetime import timedelta
        from collections import defaultdict
        
        all_subs = Submission.query.all()
        graded_subs = [s for s in all_subs if s.grade]
        class_avg = round(sum(s.grade.score for s in graded_subs) / len(graded_subs), 1) if graded_subs else 0.0
        active_count = len(set(s.student_id for s in all_subs))
        pending_count = len(all_subs) - len(graded_subs)
        
        # Prepare sparkline data for last 7 days
        today = datetime.utcnow().date()
        last_7_days = [today - timedelta(days=i) for i in range(6, -1, -1)]  # Last 7 days including today
        
        # Count submissions per day
        submissions_by_date = defaultdict(int)
        pending_by_date = defaultdict(int)
        avg_score_by_date = defaultdict(list)
        active_students_by_date = defaultdict(set)
        
        for sub in all_subs:
            sub_date = sub.created_at.date()
            if sub_date in last_7_days:
                submissions_by_date[sub_date] += 1
                if not sub.grade:
                    pending_by_date[sub_date] += 1
                if sub.grade:
                    avg_score_by_date[sub_date].append(sub.grade.score)
                active_students_by_date[sub_date].add(sub.student_id)
        
        # Create sparkline data arrays
        sparkline_data = {
            'submissions': [submissions_by_date.get(date, 0) for date in last_7_days],
            'pending': [pending_by_date.get(date, 0) for date in last_7_days],
            'class_avg': [round(sum(avg_score_by_date.get(date, [])) / len(avg_score_by_date.get(date, [])), 1) if avg_score_by_date.get(date, []) else 0.0 for date in last_7_days],
            'active_students': [len(active_students_by_date.get(date, set())) for date in last_7_days]
        }

        return render_template('instructor_dashboard.html', 
                               submissions=all_subs, 
                               class_avg=class_avg, 
                               active_count=active_count,
                               pending_count=pending_count,
                               sparkline_data=sparkline_data)
        
        
        

    # --- SUBMISSION ROUTES ---

    @app.route('/submit/writing', methods=['GET', 'POST'])
    @role_required('Student')
    def submit_writing():
        activity_id = request.args.get('activity_id')
        if request.method == 'POST':
            file = request.files.get('file')
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                text_content = ""
                if filename.endswith('.docx'):
                    doc = docx.Document(file_path)
                    text_content = "\n".join([p.text for p in doc.paragraphs])
                else:
                    with open(file_path, 'r', encoding='utf-8') as f: text_content = f.read()

                new_sub = Submission(student_id=current_user.id, activity_id=activity_id,
                                     submission_type='WRITING', file_path=filename, text_content=text_content)
                db.session.add(new_sub)
                db.session.commit()

                ai_res = AIService.evaluate_writing(text_content)
                if ai_res:
                    grade = Grade(submission_id=new_sub.id, score=ai_res.get('score', 0),
                                  general_feedback=ai_res.get('general_feedback', ""))
                    db.session.add(grade)
                    db.session.commit()
                
                flash("Submission analyzed!", "success")
                return redirect(url_for('dashboard'))
        return render_template('submit_writing.html')

    @app.route('/submit/handwritten', methods=['GET', 'POST'])
    @role_required('Student')
    def submit_handwritten():
        activity_id = request.args.get('activity_id')
        image_path = None
        extracted_text = None
        
        if request.method == 'POST':
            file = request.files.get('file')
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                extracted_text = OCRService.extract_text_from_image(file_path)
                if extracted_text:
                    new_sub = Submission(student_id=current_user.id, activity_id=activity_id,
                                         submission_type='HANDWRITTEN', file_path=filename, text_content=extracted_text)
                    db.session.add(new_sub)
                    db.session.commit()
                    
                    ai_res = AIService.evaluate_writing(extracted_text)
                    if ai_res:
                        grade = Grade(submission_id=new_sub.id, score=ai_res.get('score', 0), general_feedback=ai_res.get('general_feedback', ""))
                        db.session.add(grade)
                        db.session.commit()
                    
                    # Set image path for display (relative to static folder)
                    image_path = f"uploads/{filename}"
                    flash("Image processed successfully!", "success")
                    
        return render_template('submit_handwritten.html', 
                               image_path=image_path,
                               extracted_text=extracted_text)

    @app.route('/history')
    @login_required
    def history():
        filter_type = request.args.get('filter')
        query = Submission.query.filter_by(student_id=current_user.id)
        
        # Apply filter if specified
        if filter_type:
            if filter_type == 'speaking':
                query = query.filter_by(submission_type='SPEAKING')
            elif filter_type == 'writing':
                query = query.filter_by(submission_type='WRITING')
            elif filter_type == 'handwritten':
                query = query.filter_by(submission_type='HANDWRITTEN')
            elif filter_type == 'quiz':
                query = query.filter_by(submission_type='QUIZ')
        
        submissions = query.order_by(Submission.created_at.desc()).all()
        return render_template('history.html', submissions=submissions)

    @app.route('/feedback/<int:submission_id>')
    @login_required
    def view_feedback(submission_id):
        sub = Submission.query.get_or_404(submission_id)
        # Ensure user can only view their own submissions (unless instructor)
        if current_user.role != 'Instructor' and sub.student_id != current_user.id:
            flash("You don't have permission to view this report.", "error")
            return redirect(url_for('dashboard'))
        return render_template('feedback.html', submission=sub)

    @app.route('/delete_submission/<int:submission_id>', methods=['POST'])
    @login_required
    def delete_submission(submission_id):
        from flask import jsonify
        sub = Submission.query.get_or_404(submission_id)
        # Ensure user can only delete their own submissions
        if sub.student_id != current_user.id:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        
        try:
            # Delete associated grade if exists
            if sub.grade:
                db.session.delete(sub.grade)
            
            # Delete submission
            db.session.delete(sub)
            db.session.commit()
            
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/privacy')
    def privacy():
        return render_template('privacy.html')

    @app.route('/terms')
    def terms():
        return render_template('terms.html')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)