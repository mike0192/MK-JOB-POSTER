from flask import Flask, render_template, jsonify, request, redirect, url_for, session, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
from werkzeug.utils import secure_filename
from datetime import datetime

import cloudinary
import cloudinary.uploader
import cloudinary.api

import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///amco.db'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

app.config['ALLOWED_EXTENSIONS_VIDEO'] = {}

db = SQLAlchemy(app)
migrate = Migrate(app, db)
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


class AppliedJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    father_name = db.Column(db.String(100), nullable=False)
    applicant_email = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(10), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    cv_path = db.Column(db.String(100), nullable=True)

    def log_action(self, action, details):
        log_entry = ActionHistory(
            entity_type='AppliedJob',
            entity_id=self.id,
            action=action,
            details=details
        )
        db.session.add(log_entry)
        db.session.commit()



class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    requirements = db.Column(db.String(500), nullable=False)
    deadline = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    def __init__(self, *args, **kwargs):
        super(Job, self).__init__(*args, **kwargs)
        self.check_availability()

    def check_availability(self):
        if self.deadline and self.deadline < datetime.now():
            self.is_active = False
            db.session.commit()


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/vadmin/add_job', methods=['GET', 'POST'])
def add_job():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        requirements = request.form['requirements']
        deadline = datetime.strptime(request.form['deadline'], '%Y-%m-%dT%H:%M')

        job = Job(title=title, description=description, requirements=requirements, deadline=deadline)
        db.session.add(job)
        db.session.commit()

        job.log_action('Added', f"Job '{title}' added successfully.")

        return "Job added successfully!"

    return render_template('add_job.html')


@app.route('/vadmin/delete_job/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    job = Job.query.get(job_id)
    db.session.delete(job)
    db.session.commit()

    job.log_action('Deleted', f"Job '{job.title}' deleted successfully.")

    return redirect(url_for('vadmin'))

@app.route('/')
@app.route('/vacancy')
def vacancy():
    jobs = Job.query.filter_by(is_active=True).all()
    return render_template('vacancy.html', jobs=jobs)


@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        search_term = request.form['search_term']
        jobs = Job.query.filter(Job.title.ilike(f'%{search_term}%')).all()
        return render_template('search_results.html', jobs=jobs, search_term=search_term)
    return redirect(url_for('home'))

@app.route('/lagin', methods=['GET', 'POST'])
def lagin():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == 'admin' and password == 'admin':
            session['admin_logged_in'] = True
            return redirect(url_for('vadmin'))
        else:
            return render_template('lagin.html', error='Invalid username or password')

    return render_template('lagin.html')

@app.route('/lagout')
def lagout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('lagin'))

@app.route('/apply/<int:job_id>', methods=['GET', 'POST'])
def apply(job_id):
    job = Job.query.get(job_id)
    current_time = datetime.now()  # Get the current time

    if job.deadline and job.deadline < current_time:
        return render_template('apply.html', job=job, error='Application deadline has passed.', current_time=current_time)

    if request.method == 'POST':
        first_name = request.form['first_name']
        father_name = request.form['father_name']
        email = request.form['email']
        gender = request.form['gender']
        age = request.form['age']
        cv = request.files['cv']
        cv.save(os.path.join(app.config['UPLOAD_FOLDER'], cv.filename))

        applied_job = AppliedJob(
            job_id=job_id,
            first_name=first_name,
            father_name=father_name,
            applicant_email=email,
            gender=gender,
            age=age,
            cv_path=f"uploads/{cv.filename}"
        )
        db.session.add(applied_job)
        db.session.commit()

        return redirect(url_for('vacancy'))

    return render_template('apply.html', job=job, current_time=current_time)

@app.route('/lagin/vadmin')
def vadmin():
    jobs = Job.query.all()
    return render_template('vadmin.html', jobs=jobs)

@app.route('/vadmin/applied_jobs/<int:job_id>')
def applied_jobs(job_id):
    applied_jobs = AppliedJob.query.filter_by(job_id=job_id).all()
    return render_template('applied_jobs.html', applied_jobs=applied_jobs, job_id=job_id)

@app.route('/vadmin/delete_applied_job/<int:applied_job_id>', methods=['POST'])
def delete_applied_job(applied_job_id):
    applied_job = AppliedJob.query.get(applied_job_id)
    db.session.delete(applied_job)
    db.session.commit()

    applied_job.log_action('Deleted', f"Applied job with ID '{applied_job_id}' deleted successfully.")

    return redirect(url_for('applied_jobs', job_id=applied_job.job_id))

@app.route('/download_cv/<path:cv_path>')
def download_cv(cv_path):
    cv_directory = app.config['UPLOAD_FOLDER']
    filename = os.path.basename(cv_path)
    return send_from_directory(cv_directory, filename, as_attachment=True)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)