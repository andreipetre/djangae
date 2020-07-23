from djangae.contrib.googleauth import (
    _get_backends,
    load_backend,
)
from django.contrib.auth.base_user import (
    AbstractBaseUser,
    BaseUserManager,
)
from djangae.contrib.googleauth.validators import UnicodeUsernameValidator
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from gcloudc.db.models.fields.iterable import SetField
from gcloudc.db.models.fields.json import JSONField

from .permissions import PermissionChoiceField


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, username, email, password, **extra_fields):
        """
        Create and save a user with the given username, email, and password.
        """
        if not username:
            raise ValueError('The given username must be set')
        email = self.normalize_email(email)
        username = self.model.normalize_username(username)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)

    def with_perm(self, perm, is_active=True, include_superusers=True, backend=None, obj=None):
        if backend is None:
            backends = _get_backends(return_tuples=True)
            if len(backends) == 1:
                backend, _ = backends[0]
            else:
                raise ValueError(
                    'You have multiple authentication backends configured and '
                    'therefore must provide the `backend` argument.'
                )
        elif not isinstance(backend, str):
            raise TypeError(
                'backend must be a dotted import path string (got %r).'
                % backend
            )
        else:
            backend = load_backend(backend)
        if hasattr(backend, 'with_perm'):
            return backend.with_perm(
                perm,
                is_active=is_active,
                include_superusers=include_superusers,
                obj=obj,
            )
        return self.none()


class AnonymousUser:
    id = None
    pk = None
    username = ''
    is_staff = False
    is_active = False
    is_superuser = False

    def __str__(self):
        return 'AnonymousUser'

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __hash__(self):
        return 1  # instances always return the same hash value

    def __int__(self):
        raise TypeError('Cannot cast AnonymousUser to int. Are you trying to use it in place of User?')

    def save(self):
        raise NotImplementedError("Djangae doesn't provide a DB representation for AnonymousUser.")

    def delete(self):
        raise NotImplementedError("Djangae doesn't provide a DB representation for AnonymousUser.")

    def set_password(self, raw_password):
        raise NotImplementedError("Djangae doesn't provide a DB representation for AnonymousUser.")

    def check_password(self, raw_password):
        raise NotImplementedError("Djangae doesn't provide a DB representation for AnonymousUser.")

    @property
    def groups(self):
        return self._groups

    @property
    def user_permissions(self):
        return self._user_permissions

    def get_group_permissions(self, obj=None):
        return set()

    def get_all_permissions(self, obj=None):
        return []

    def has_perm(self, perm, obj=None):
        return False

    def has_perms(self, perm_list, obj=None):
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, module):
        return False

    @property
    def is_anonymous(self):
        return True

    @property
    def is_authenticated(self):
        return False

    def get_username(self):
        return self.username


class User(AbstractBaseUser):
    username_validator = UnicodeUsernameValidator()

    username = models.CharField(
        _('username'),
        max_length=150,
        unique=True,
        help_text=_('Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.'),
        validators=[username_validator],
        error_messages={
            'unique': _("A user with that username already exists."),
        },
    )
    first_name = models.CharField(_('first name'), max_length=150, blank=True)
    last_name = models.CharField(_('last name'), max_length=150, blank=True)
    email = models.EmailField(_('email address'), blank=True)
    is_staff = models.BooleanField(
        _('staff status'),
        default=False,
        help_text=_('Designates whether the user can log into this admin site.'),
    )
    is_superuser = models.BooleanField(
        _('superuser status'),
        default=False,
        help_text=_(
            'Designates that this user has all permissions without '
            'explicitly assigning them.'
        ),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    objects = UserManager()

    EMAIL_FIELD = 'email'
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        # abstract = True

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Send an email to this user."""
        send_mail(subject, message, from_email, [self.email], **kwargs)


class UserPermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="permissions")
    permission = PermissionChoiceField()
    obj_id = models.PositiveIntegerField()


class Group(models.Model):
    name = models.CharField(_('name'), max_length=150, unique=True)
    permissions = SetField(
        PermissionChoiceField(),
        blank=True
    )

    def __str__(self):
        return self.name


class AppOAuthCredentials(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    client_id = models.CharField(max_length=150, default="")
    client_secret = models.CharField(max_length=150, default="")

    @classmethod
    def get(cls):
        from djangae.environment import application_id
        return cls.objects.get(
            pk=application_id()
        )

    @classmethod
    def get_or_create(cls, **kwargs):
        from djangae.environment import application_id
        return cls.objects.get_or_create(
            pk=application_id(),
            defaults=kwargs
        )[0]


# Set in the Django session in the oauth2callback. This is used
# by the backend's authenticate() method
_OAUTH_USER_SESSION_SESSION_KEY = "_OAUTH_USER_SESSION_ID"


class OAuthUserSession(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    authorization_code = models.CharField(max_length=150, blank=True)

    access_token = models.CharField(max_length=150, blank=True)
    refresh_token = models.CharField(max_length=150, blank=True)
    id_token = models.CharField(max_length=1500, blank=True)
    token_type = models.CharField(max_length=150, blank=True)
    expires_at = models.CharField(max_length=150, blank=True)
    expires_in = models.CharField(max_length=150, blank=True)

    scopes = SetField(models.CharField(max_length=1500), blank=True)
    token = JSONField(blank=True)

    def is_valid(self):
        pass

    def refresh(self):
        pass
