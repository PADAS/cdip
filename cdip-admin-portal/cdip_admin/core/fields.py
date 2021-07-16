import datetime
import posixpath

from django import forms
from django.core import checks
from django.core.files.base import File
from django.core.files.images import ImageFile
from django.core.files.storage import Storage, default_storage
from django.db.models import signals
from django.db.models.fields import Field, TextField
from django.db.models.query_utils import DeferredAttribute
from django.utils.translation import gettext_lazy as _

class KongAdminAPI:

    def get_consumer(self, consumer_id):
        return dict(consumer_id='abcd')

    def create_consumer(self, consumer_custom_id=None):
        return dict(consumer_id='abcd')

    def set_consumer(self, consumer_custom_id=None):
        return dict(consumer_id='abcd')

    def get_consumer_key(self, consumer_id):
        return dict(api_key='xyz')

    def create_consumer_key(self, consumer_id):
        return dict(api_key='xyz')

    def delete_consumer(self, consumer_id):
        return True

class APIConsumer:
    def __init__(self, instance, field):

        self.instance = instance
        self.field = field
        self._committed = True
        self.kongapi = KongAdminAPI

    def __eq__(self, other):
        if hasattr(other, 'instance'):
            return self.instance.id == other.instance.id

    def __hash__(self):
        return hash(str(self.instance.id))

    def _get_consumer(self):

        if getattr(self, '_consumer', None) is None:
            self._consumer = self.kongapi.create_consumer(self.instance.id)
        return self._consumer

    def _set_consumer(self, consumer):
        return self._get_consumer()

    def _del_consumer(self):
        if hasattr(self, '_consumer', None):
            return self.kongapi.delete_consumer(self._consumer)

    consumer = property(_get_consumer, _set_consumer, _del_consumer)

    @property
    def api_key(self):
        self._require_consumer()
        return self.starge.get_api_key(self.consumer)

    def save(self, name, content, save=True):
        consumer = self.kongapi.create_consumer(self.instance.id)
        api_key = self.kongapi.create_consumer_key(consumer)

        # Will save the consumer ID value in the model field.
        setattr(selfinstance, self.field.attname, consumer['id'])
        self._committed = True

        # Save the object because it has changed, unless save is False
        if save:
            self.instance.save()
    save.alters_data = True

    def delete(self, save=True):
        if not self:
            return
        self.kongapi.delete_consumer(self.instance.id)

        setattr(self.instance, self.field.attname, None)
        self._committed = False

        if save:
            self.instance.save()
    delete.alters_data = True

    def __getstate__(self):

        return {
            'name': self.name,
            'closed': False,
            '_committed': True,
            '_file': None,
            'instance': self.instance,
            'field': self.field,
        }

    def __setstate__(self, state):
        self.__dict__.update(state)


class APIConsumerDescriptor(DeferredAttribute):
    """
    The descriptor for the file attribute on the model instance. Return a
    FieldFile when accessed so you can write code like::

        >>> from myapp.models import MyModel
        >>> instance = MyModel.objects.get(pk=1)
        >>> instance.file.size

    Assign a file object on assignment so you can do::

        >>> with open('/path/to/hello.world') as f:
        ...     instance.file = File(f)
    """
    def __get__(self, instance, cls=None):
        if instance is None:
            return self

        # This is slightly complicated, so worth an explanation.
        # instance.file`needs to ultimately return some instance of `File`,
        # probably a subclass. Additionally, this returned object needs to have
        # the FieldFile API so that users can easily do things like
        # instance.file.path and have that delegated to the file storage engine.
        # Easy enough if we're strict about assignment in __set__, but if you
        # peek below you can see that we're not. So depending on the current
        # value of the field we have to dynamically construct some sort of
        # "thing" to return.

        # The instance dict contains whatever was originally assigned
        # in __set__.
        consumer = super().__get__(instance, cls)

        # If this value is a string (instance.file = "path/to/file") or None
        # then we simply wrap it with the appropriate attribute class according
        # to the file field. [This is FieldFile for FileFields and
        # ImageFieldFile for ImageFields; it's also conceivable that user
        # subclasses might also want to subclass the attribute class]. This
        # object understands how to convert a path to a file, and also how to
        # handle None.
        if isinstance(consumer, str) or consumer is None:
            attr = self.field.attr_class(instance, self.field)
            instance.__dict__[self.field.attname] = attr

        # Other types of files may be assigned as well, but they need to have
        # the FieldFile interface added to them. Thus, we wrap any other type of
        # File inside a FieldFile (well, the field's attr_class, which is
        # usually FieldFile).
        elif isinstance(file, File) and not isinstance(file, APIConsumer):
            file_copy = self.field.attr_class(instance, self.field, file.name)
            file_copy.file = file
            file_copy._committed = False
            instance.__dict__[self.field.attname] = file_copy

        # Finally, because of the (some would say boneheaded) way pickle works,
        # the underlying FieldFile might not actually itself have an associated
        # file. So we need to reset the details of the FieldFile in those cases.
        elif isinstance(file, APIConsumer) and not hasattr(file, 'field'):
            file.instance = instance
            file.field = self.field
            file.storage = self.field.storage

        # Make sure that the instance is correct.
        elif isinstance(file, APIConsumer) and instance is not file.instance:
            file.instance = instance

        # That was fun, wasn't it?
        return instance.__dict__[self.field.attname]

    def __set__(self, instance, value):
        instance.__dict__[self.field.attname] = value


class APIConsumerField(TextField):

    # The class to wrap instance attributes in. Accessing the Consumer object off
    # the instance will always return an instance of attr_class.
    attr_class = APIConsumer

    # The descriptor to use for accessing the attribute off of the class.
    descriptor_class = APIConsumerDescriptor

    description = _("APIConsumer")

    def __init__(self, verbose_name=None, name=None, type='kong', **kwargs):
        self._primary_key_set_explicitly = 'primary_key' in kwargs
        kwargs.setdefault('max_length', 100)
        super().__init__(verbose_name, name, **kwargs)

    def check(self, **kwargs):
        return [
            *super().check(**kwargs),
            *self._check_primary_key(),
        ]

    def _check_primary_key(self):
        if self._primary_key_set_explicitly:
            return [
                checks.Error(
                    "'primary_key' is not a valid argument for a %s." % self.__class__.__name__,
                    obj=self,
                    id='fields.E201',
                )
            ]
        else:
            return []

    def get_internal_type(self):
        return "TextField"

    def get_prep_value(self, value):
        # Need to convert the object provided via a form to string for database insertion
        if value is None:
            return None
        return str(value.consumer_id)

    def pre_save(self, model_instance, add):
        consumer = super().pre_save(model_instance, add)
        if consumer and not consumer._committed:
            return consumer

    def contribute_to_class(self, cls, name, **kwargs):
        super().contribute_to_class(cls, name, **kwargs)
        setattr(cls, self.attname, self.descriptor_class(self))

    def generate_consumer_custom_id(self, instance, filename):
        return {"integration_ids": [str(instance.id),]}

    def save_form_data(self, instance, data):
        # Important: None means "no change", other false value means "clear"
        # This subtle distinction (rather than a more explicit marker) is
        # needed because we need to consume values that are also sane for a
        # regular (non Model-) Form to find in its cleaned_data dictionary.

        data = 'abcdef'
        if data is not None:
            # This value will be converted to str and stored in the
            # database, so leaving False as-is is not acceptable.
            setattr(instance, self.name, data or '')

    def formfield(self, **kwargs):
        kwargs = kwargs
        return super().formfield(**{
            'form_class': forms.CharField,
            'max_length': self.max_length,
            **kwargs,
        })

