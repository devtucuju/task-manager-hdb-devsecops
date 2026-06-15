"""Formulários WTForms com CSRF e validação de senha forte."""
import re

from flask_wtf import FlaskForm
from wtforms import (
    DateField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from todo_project.auth import validate_password_strength
from todo_project.extensions import db
from todo_project.models import User


class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Senhas devem coincidir.')],
    )
    submit = SubmitField('Register')

    def validate_username(self, username):
        if db.session.query(User.id).filter_by(username=username.data).first():
            raise ValidationError('Username já existe.')

    def validate_email(self, email):
        if db.session.query(User.id).filter_by(email=email.data.lower()).first():
            raise ValidationError('Email já cadastrado.')

    def validate_password(self, password):
        valid, message = validate_password_strength(password.data)
        if not valid:
            raise ValidationError(message)


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class UpdateUserInfoForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    submit = SubmitField('Update Info')

    def validate_username(self, field):
        from flask import g
        existing = db.session.query(User).filter(
            User.username == field.data.strip(),
            User.id != g.current_user.id,
        ).first()
        if existing:
            raise ValidationError('Username já existe.')

    def validate_email(self, field):
        from flask import g
        existing = db.session.query(User).filter(
            User.email == field.data.lower().strip(),
            User.id != g.current_user.id,
        ).first()
        if existing:
            raise ValidationError('Email já cadastrado.')


class UpdateUserPasswordForm(FlaskForm):
    old_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=8, max=128)])
    submit = SubmitField('Change Password')

    def validate_new_password(self, new_password):
        valid, message = validate_password_strength(new_password.data)
        if not valid:
            raise ValidationError(message)


class TaskForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=1, max=120)])
    description = TextAreaField('Description', validators=[Length(max=2000)])
    priority = SelectField(
        'Priority',
        choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        default='medium',
    )
    status = SelectField(
        'Status',
        choices=[('pending', 'Pending'), ('in_progress', 'In Progress'), ('done', 'Done')],
        default='pending',
    )
    category = StringField('Category', validators=[Length(max=50)])
    due_date = DateField('Due Date', format='%Y-%m-%d', validators=[])
    submit = SubmitField('Save Task')
