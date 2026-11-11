from django.contrib import admin
from .models import Department,Profile,Category,Ticket,Event,Comment,Attachment,Notification
@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display=['id','title','status','assignee','department','due_at']
    list_filter=['status','department','category']
    readonly_fields=[f.name for f in Ticket._meta.fields]
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
admin.site.register([Department,Profile,Category])
admin.site.site_header='Модус · Настройки системы'
