import csv
import io
import os
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, text

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ['SECRET_KEY'], SQLALCHEMY_DATABASE_URI=os.environ['DATABASE_URL'],
                  SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True}, MAX_CONTENT_LENGTH=16384,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
db = SQLAlchemy(app)
TOPICS = [
    ('Getting Ready, Starting, Placing Vehicle in Motion, and Stopping', 2),
    ('Moving, Stopping, Steering, Knowing Where You Are', 3), ('Backing', 1),
    ('Turning, Lane Position, and Visual Skills', 4), ('Searching Intended Path of Travel', 3),
    ('Parking', 1), ('Turnabouts', 2), ('Multiple Lane Roadways', 4), ('City Driving', 5),
    ('Expressway/Freeway Driving', 5)]


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, default='')
    permit = db.Column(db.String(60), nullable=False, default='')


class Drive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    topic = db.Column(db.Integer, nullable=False)
    day = db.Column(db.Integer, nullable=False)
    night = db.Column(db.Integer, nullable=False)
    initials = db.Column(db.String(20), nullable=False)
    license = db.Column(db.String(60), nullable=False)
    notes = db.Column(db.String(2000), nullable=False, default='')
    __table_args__ = (db.CheckConstraint('day >= 0 AND night >= 0 AND day + night BETWEEN 1 AND 120'),
                      db.CheckConstraint('topic BETWEEN 0 AND 9'))


def today():
    return datetime.now(ZoneInfo('America/Chicago')).date()


@app.template_filter('hours')
def hours(minutes):
    return f'{minutes / 60:.2f}'.rstrip('0').rstrip('.')


@app.before_request
def csrf():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(32)
    if request.method == 'POST' and not secrets.compare_digest(session['csrf'], request.form.get('csrf', '')):
        abort(400, 'Invalid form token. Reload the page and try again.')


def bounded(field, maximum, required=True):
    value = request.form.get(field, '').strip()
    if (required and not value) or len(value) > maximum:
        raise ValueError(f'{field.title()} is required and must be at most {maximum} characters.')
    return value


def minutes(field):
    try:
        value = Decimal(request.form.get(field, '0') or '0')
        if not value.is_finite() or value < 0 or value > 120 or value != value.to_integral_value():
            raise ValueError()
        return int(value)
    except (InvalidOperation, ValueError):
        raise ValueError('Daytime and nighttime minutes must be whole numbers between 0 and 120.')


@app.get('/')
def index():
    drives = db.session.scalars(select(Drive).order_by(Drive.date.desc(), Drive.time.desc(), Drive.id.desc())).all()
    totals = [sum(d.day + d.night for d in drives if d.topic == i) for i in range(len(TOPICS))]
    night = sum(d.night for d in drives)
    return render_template('index.html', student=db.session.get(Student, 1), drives=drives,
                           topics=TOPICS, totals=totals, total=sum(totals), night=night,
                           remaining=max(1800-sum(totals), 0), night_remaining=max(600-night, 0), today=today())


@app.post('/student')
def student():
    try:
        name, permit = bounded('name', 120), bounded('permit', 60, False)
        s = db.session.get(Student, 1)
        s.name, s.permit = name, permit
        db.session.commit()
        flash('Student details saved.', 'success')
    except ValueError as exc:
        flash(str(exc), 'error')
    return redirect(url_for('index'))


@app.route('/sessions/new', methods=['GET', 'POST'])
@app.route('/sessions/<int:drive_id>/edit', methods=['GET', 'POST'])
def edit(drive_id=None):
    drive = db.get_or_404(Drive, drive_id) if drive_id else None
    if request.method == 'POST':
        try:
            day_date = date.fromisoformat(request.form.get('date', ''))
            start = datetime.strptime(request.form.get('time', ''), '%H:%M').time()
            topic = int(request.form.get('topic', '-1'))
            if day_date > today() or not 0 <= topic < len(TOPICS):
                raise ValueError('Choose a valid topic and a date that is not in the future.')
            daytime, nighttime = minutes('day'), minutes('night')
            if daytime + nighttime < 1:
                raise ValueError('Enter at least one minute of practice.')
            initials, license_number, notes = bounded('initials', 20), bounded('license', 60), bounded('notes', 2000, False)
            # Serialize changes for the single learner so concurrent submissions cannot exceed the daily cap.
            db.session.execute(select(Student).where(Student.id == 1).with_for_update()).scalar_one()
            used = db.session.scalar(select(db.func.coalesce(db.func.sum(Drive.day + Drive.night), 0)).where(
                Drive.date == day_date, Drive.id != (drive_id or 0)))
            if used + daytime + nighttime > 120:
                raise ValueError(f'The template allows 120 minutes per day. This date has {used} minutes in other sessions.')
            if drive is None:
                drive = Drive()
                db.session.add(drive)
            drive.date, drive.time, drive.topic = day_date, start, topic
            drive.day, drive.night, drive.initials, drive.license, drive.notes = daytime, nighttime, initials, license_number, notes
            db.session.commit()
            flash('Practice session saved.', 'success')
            return redirect(url_for('index'))
        except (ValueError, OverflowError) as exc:
            db.session.rollback()
            flash(str(exc) or 'Check the session values.', 'error')
            return render_template('form.html', drive=drive, values=request.form, topics=TOPICS, today=today()), 400
    values = {key: getattr(drive, key) for key in ('date', 'topic', 'day', 'night', 'initials', 'license', 'notes')} if drive else {}
    if drive:
        values['time'] = drive.time.strftime('%H:%M')
    return render_template('form.html', drive=drive, values=values, topics=TOPICS, today=today())


@app.post('/sessions/<int:drive_id>/delete')
def delete(drive_id):
    db.session.execute(select(Student).where(Student.id == 1).with_for_update()).scalar_one()
    db.session.delete(db.get_or_404(Drive, drive_id))
    db.session.commit()
    flash('Session deleted.', 'success')
    return redirect(url_for('index'))


def csv_safe(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value


@app.get('/download.csv')
def download():
    s = db.session.get(Student, 1)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Student name', 'Permit number', 'Date', 'Start time', 'Practice topic', 'Daytime minutes',
                     'Nighttime minutes', 'Daytime hours', 'Nighttime hours', 'Total hours', 'Adult initials', 'Adult DL number', 'Notes'])
    for d in db.session.scalars(select(Drive).order_by(Drive.date, Drive.time, Drive.id)):
        writer.writerow([csv_safe(s.name), csv_safe(s.permit), d.date.isoformat(), d.time.strftime('%H:%M'),
                         TOPICS[d.topic][0], d.day, d.night, f'{d.day/60:.4f}', f'{d.night/60:.4f}',
                         f'{(d.day+d.night)/60:.4f}', csv_safe(d.initials), csv_safe(d.license), csv_safe(d.notes)])
    return Response('\ufeff' + output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=driving-log-{today()}.csv', 'Cache-Control': 'no-store'})


@app.get('/health')
def health():
    db.session.execute(text('SELECT 1'))
    return {'status': 'ok'}


@app.cli.command('init-db')
def init_db():
    db.create_all()
    if not db.session.get(Student, 1):
        db.session.add(Student(id=1))
        db.session.commit()
