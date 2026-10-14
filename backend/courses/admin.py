from django.contrib import admin
from core.admin_base import InstitutionContentAdmin, InstitutionContentForm
from .models import Course, CourseModule, Album, StartupMaterial, CourseTag, CourseTagRelation, CourseOutline, OutlineItem


class CourseForm(InstitutionContentForm):
    def clean(self):
        data = super().clean()
        if not data.get('module'):
            self.add_error('module', '请选择所属模块。')
        return data


@admin.register(CourseModule)
class CourseModuleAdmin(InstitutionContentAdmin):
    list_display = ('name', 'institution', 'is_public', 'sort_order')
    list_filter = ('institution', 'is_public')
    search_fields = ('name',)
    ordering = ('sort_order', 'id')

@admin.register(Course)
class CourseAdmin(InstitutionContentAdmin):
    form = CourseForm
    list_display = ('title', 'module', 'institution', 'album_obj', 'sort_order', 'created_at')
    list_filter = ('institution', 'module', 'module__is_public')
    search_fields = ('title', 'description')
    autocomplete_fields = ('module', 'album_obj', 'knowledge_point')
    readonly_fields = ('author', 'created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        super().save_model(request, obj, form, change)

@admin.register(Album)
class AlbumAdmin(InstitutionContentAdmin):
    list_display = ('name', 'institution', 'created_at')
    search_fields = ('name',)

@admin.register(StartupMaterial)
class StartupMaterialAdmin(InstitutionContentAdmin):
    list_display = ('name', 'institution', 'created_at')
    search_fields = ('name',)


@admin.register(CourseTag)
class CourseTagAdmin(InstitutionContentAdmin):
    list_display = ('name', 'institution', 'slug')
    search_fields = ('name',)


@admin.register(CourseTagRelation)
class CourseTagRelationAdmin(InstitutionContentAdmin):
    institution_lookup = 'course__institution'
    list_display = ('course', 'tag')
    autocomplete_fields = ('course', 'tag')


class OutlineItemInline(admin.TabularInline):
    model = OutlineItem
    extra = 0


@admin.register(CourseOutline)
class CourseOutlineAdmin(InstitutionContentAdmin):
    institution_lookup = 'course__institution'
    list_display = ('course', 'status', 'updated_at')
    autocomplete_fields = ('course',)
    inlines = (OutlineItemInline,)
