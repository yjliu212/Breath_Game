from flask import (Flask, render_template, request, redirect, url_for, flash,
                   jsonify, send_from_directory)
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text, func
from sqlalchemy.exc import OperationalError
from datetime import datetime, date, timedelta, timezone
import math
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = '请先登录。'

# ---------------------------------------------------------------------------
# Breathing settings: allowed ranges (seconds) and defaults
# ---------------------------------------------------------------------------
SETTING_FIELDS = {
    # name: (label, min, max, default)
    'inhale': ('吸气', 1.0, 30.0, 4.0),
    'hold1': ('吸气后屏息', 0.0, 30.0, 2.0),
    'exhale': ('呼气', 1.0, 30.0, 6.0),
    'hold2': ('呼气后屏息', 0.0, 30.0, 2.0),
}
ROUNDS_MIN, ROUNDS_MAX, ROUNDS_DEFAULT = 1, 50, 5
PATTERNS = {'relax', '478', 'box', 'coherent', 'custom'}
MAX_SESSIONS_PER_DAY = 200


def parse_setting(name, raw):
    """Validate one breathing-phase duration. Returns (value, error_message)."""
    label, lo, hi, _ = SETTING_FIELDS[name]
    if raw is None or (isinstance(raw, str) and raw.strip() == ''):
        return None, f'{label}时间不能为空。'
    if isinstance(raw, bool):
        return None, f'{label}时间必须是数字。'
    try:
        value = float(raw.strip() if isinstance(raw, str) else raw)
    except (TypeError, ValueError):
        return None, f'{label}时间必须是数字。'
    if not math.isfinite(value):
        return None, f'{label}时间必须是有效数字。'
    if value < 0:
        return None, f'{label}时间不能为负数。'
    if value < lo or value > hi:
        return None, f'{label}时间需在 {lo:g}–{hi:g} 秒之间。'
    return round(value, 1), None


def parse_rounds(raw):
    if raw is None or (isinstance(raw, str) and raw.strip() == ''):
        return None, '轮数不能为空。'
    if isinstance(raw, bool):
        return None, '轮数必须是整数。'
    try:
        value = float(raw.strip() if isinstance(raw, str) else raw)
    except (TypeError, ValueError):
        return None, '轮数必须是整数。'
    if not math.isfinite(value) or value != int(value):
        return None, '轮数必须是整数。'
    if not ROUNDS_MIN <= value <= ROUNDS_MAX:
        return None, f'轮数需在 {ROUNDS_MIN}–{ROUNDS_MAX} 之间。'
    return int(value), None


def safe_setting(name, value):
    """Return a stored value if it is valid, otherwise the default (for legacy bad rows)."""
    _, lo, hi, default = SETTING_FIELDS[name]
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v) or v < lo or v > hi:
        return default
    return v


def safe_rounds(value):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return ROUNDS_DEFAULT
    return v if ROUNDS_MIN <= v <= ROUNDS_MAX else ROUNDS_DEFAULT


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    inhale = db.Column(db.Float, default=4.0)
    hold1 = db.Column(db.Float, default=2.0)
    exhale = db.Column(db.Float, default=6.0)
    hold2 = db.Column(db.Float, default=2.0)
    # Added after the first release; see ADDED_COLUMNS for the migration.
    rounds = db.Column(db.Integer, default=ROUNDS_DEFAULT, server_default=str(ROUNDS_DEFAULT))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class PracticeSession(db.Model):
    __tablename__ = 'practice_session'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    completed_at = db.Column(db.DateTime, nullable=False,
                             default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    local_date = db.Column(db.Date, nullable=False, index=True)
    duration_seconds = db.Column(db.Float, nullable=False)
    rounds = db.Column(db.Integer, nullable=False)
    inhale = db.Column(db.Float, nullable=False)
    hold1 = db.Column(db.Float, nullable=False)
    exhale = db.Column(db.Float, nullable=False)
    hold2 = db.Column(db.Float, nullable=False)
    pattern = db.Column(db.String(20), nullable=False, default='custom')


# Columns added to pre-existing tables after the first production release.
# (table, column, SQL type + default). Only ever append to this list.
ADDED_COLUMNS = [
    ('user', 'rounds', f'INTEGER DEFAULT {ROUNDS_DEFAULT}'),
]


def init_db():
    """Create missing tables and add missing columns. Never drops anything."""
    try:
        db.create_all()
    except OperationalError as exc:  # another worker created it concurrently
        if 'already exists' not in str(exc):
            raise
    insp = inspect(db.engine)
    for table, column, ddl in ADDED_COLUMNS:
        existing = {c['name'] for c in insp.get_columns(table)}
        if column in existing:
            continue
        try:
            with db.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))
        except OperationalError as exc:
            if 'duplicate column' not in str(exc):
                raise


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def compute_stats(user_id, today=None):
    """Total sessions, total minutes and current streak (consecutive local days).

    Dates are the user's local dates sent by the browser. Because the server does
    not know the user's timezone, a streak is still "alive" if the last practice
    day is today or yesterday relative to the server's UTC date (with one day of
    tolerance for timezones ahead of UTC).
    """
    if today is None:
        today = datetime.now(timezone.utc).date()
    count, seconds = db.session.query(
        func.count(PracticeSession.id), func.coalesce(func.sum(PracticeSession.duration_seconds), 0)
    ).filter(PracticeSession.user_id == user_id).one()
    days = {d for (d,) in db.session.query(PracticeSession.local_date)
            .filter(PracticeSession.user_id == user_id).distinct()}
    streak = 0
    if days:
        last = max(days)
        if last >= today - timedelta(days=1):
            d = last
            while d in days:
                streak += 1
                d -= timedelta(days=1)
    return {
        'sessions': int(count),
        'minutes': round(float(seconds) / 60, 1),
        'streak': streak,
    }


# ---------------------------------------------------------------------------
# Forms
# ---------------------------------------------------------------------------
class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired('请输入用户名'), Length(min=2, max=150, message='用户名长度需为 2–150 个字符')])
    password = PasswordField('密码', validators=[DataRequired('请输入密码')])
    submit = SubmitField('登录')


class RegisterForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired('请输入用户名'), Length(min=2, max=150, message='用户名长度需为 2–150 个字符')])
    password = PasswordField('密码', validators=[DataRequired('请输入密码'), Length(min=6, message='密码至少 6 位')])
    submit = SubmitField('注册')


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def database_uri(app):
    """SQLALCHEMY_DATABASE_URI > DATABASE_PATH > /home/data on App Service > instance/users.db."""
    uri = os.environ.get('SQLALCHEMY_DATABASE_URI')
    if uri:
        return uri
    path = os.environ.get('DATABASE_PATH')
    if not path:
        if os.environ.get('WEBSITE_SITE_NAME'):
            # Running on Azure App Service: keep the DB outside wwwroot so deploys don't wipe it.
            path = '/home/data/users.db'
        else:
            path = os.path.join(app.instance_path, 'users.db')
    return 'sqlite:///' + os.path.abspath(path)


def ensure_sqlite_dir(uri):
    if uri.startswith('sqlite:///') and ':memory:' not in uri:
        parent = os.path.dirname(uri[len('sqlite:///'):])
        if parent:
            os.makedirs(parent, exist_ok=True)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_uri(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    if test_config:
        app.config.update(test_config)
    ensure_sqlite_dir(app.config['SQLALCHEMY_DATABASE_URI'])

    db.init_app(app)
    login_manager.init_app(app)
    register_routes(app)

    with app.app_context():
        init_db()
    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def register_routes(app):

    @app.route("/")
    def home():
        settings = None
        stats = None
        if current_user.is_authenticated:
            settings = {name: safe_setting(name, getattr(current_user, name)) for name in SETTING_FIELDS}
            settings['rounds'] = safe_rounds(current_user.rounds)
            stats = compute_stats(current_user.id)
        limits = {name: {'label': f[0], 'min': f[1], 'max': f[2], 'default': f[3]}
                  for name, f in SETTING_FIELDS.items()}
        limits['rounds'] = {'label': '轮数', 'min': ROUNDS_MIN, 'max': ROUNDS_MAX, 'default': ROUNDS_DEFAULT}
        return render_template("Breath_Game.html", settings=settings, stats=stats, limits=limits)

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user and user.check_password(form.password.data):
                login_user(user)
                return redirect(url_for('home'))
            flash('用户名或密码错误', 'error')
        return render_template('login.html', form=form)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        form = RegisterForm()
        if form.validate_on_submit():
            user = User.query.filter_by(username=form.username.data).first()
            if user:
                flash('用户名已存在', 'error')
            else:
                new_user = User(username=form.username.data)
                new_user.set_password(form.password.data)
                db.session.add(new_user)
                db.session.commit()
                login_user(new_user)
                flash('注册成功，欢迎！', 'success')
                return redirect(url_for('home'))
        return render_template('register.html', form=form)

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('home'))

    @app.route('/save_settings', methods=['POST'])
    @login_required
    def save_settings():
        values, errors = {}, []
        for name in SETTING_FIELDS:
            value, err = parse_setting(name, request.form.get(name))
            if err:
                errors.append(err)
            values[name] = value
        # rounds is optional for backwards compatibility with old clients
        if request.form.get('rounds') is not None:
            values['rounds'], err = parse_rounds(request.form.get('rounds'))
            if err:
                errors.append(err)
        if errors:
            for err in errors:
                flash(err, 'error')
            flash('设置未保存，请修正后重试。', 'error')
            return redirect(url_for('home'))
        for name, value in values.items():
            setattr(current_user, name, value)
        db.session.commit()
        flash('设置已保存！', 'success')
        return redirect(url_for('home'))

    @app.route('/api/sessions', methods=['POST'])
    def record_session():
        if not current_user.is_authenticated:
            return jsonify(ok=False, error='请先登录。'), 401
        data = request.get_json(silent=True) if request.is_json else None
        if not isinstance(data, dict):
            return jsonify(ok=False, error='请求格式错误。'), 400

        errors, values = [], {}
        for name in SETTING_FIELDS:
            values[name], err = parse_setting(name, data.get(name))
            if err:
                errors.append(err)
        values['rounds'], err = parse_rounds(data.get('rounds'))
        if err:
            errors.append(err)
        pattern = data.get('pattern', 'custom')
        if pattern not in PATTERNS:
            errors.append('未知的呼吸模式。')

        server_today = datetime.now(timezone.utc).date()
        try:
            local_date = date.fromisoformat(str(data.get('local_date', '')))
        except ValueError:
            local_date = None
            errors.append('日期格式错误。')
        if local_date and abs((local_date - server_today).days) > 1:
            errors.append('日期不合理。')
        if errors:
            return jsonify(ok=False, error=' '.join(errors)), 400

        cycle = sum(values[n] for n in SETTING_FIELDS)
        duration = round(cycle * values['rounds'], 1)

        # Plausibility: a session cannot finish before the previous one could have.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        last = (PracticeSession.query.filter_by(user_id=current_user.id)
                .order_by(PracticeSession.completed_at.desc()).first())
        if last and (now - last.completed_at).total_seconds() < duration - 2:
            return jsonify(ok=False, error='记录过于频繁。'), 429
        today_count = PracticeSession.query.filter_by(user_id=current_user.id, local_date=local_date).count()
        if today_count >= MAX_SESSIONS_PER_DAY:
            return jsonify(ok=False, error='今日记录次数已达上限。'), 429

        db.session.add(PracticeSession(
            user_id=current_user.id, completed_at=now, local_date=local_date,
            duration_seconds=duration, pattern=pattern, **values))
        db.session.commit()
        return jsonify(ok=True, duration_seconds=duration, stats=compute_stats(current_user.id)), 201

    @app.route('/api/stats')
    def stats():
        if not current_user.is_authenticated:
            return jsonify(ok=False, error='请先登录。'), 401
        return jsonify(compute_stats(current_user.id))

    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(app.static_folder, 'favicon.svg', mimetype='image/svg+xml',
                                   max_age=86400)

    @app.route('/robots.txt')
    def robots():
        return send_from_directory(app.static_folder, 'robots.txt', mimetype='text/plain',
                                   max_age=86400)


# gunicorn imports `app:app`; creating it here also creates/migrates the DB tables.
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
