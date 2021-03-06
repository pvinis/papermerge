from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import ngettext
from django.contrib import messages
from django.utils.translation import ugettext_lazy as _
from django.views import View

from papermerge.search.backends import get_search_backend
from papermerge.core.models import (
    Page,
    Folder,
    BaseTreeNode,
    Access,
    Tag
)

from .models import LogEntry
from .forms import (
    LogEntryForm,
    TagForm
)


@login_required
def browse(request):
    return render(
        request,
        "admin/index.html"
    )


@login_required
def inbox_view(request):

    try:
        inbox = Folder.objects.get(
            title=Folder.INBOX_NAME,
            user=request.user
        )
        root_node_id = inbox.id

    except Folder.DoesNotExist:
        root_node_id = None

    return render(
        request,
        "admin/index.html",
        {
            'root_node_id': root_node_id
        }
    )


@login_required
def search(request):
    search_term = request.GET.get('q')
    backend = get_search_backend()

    results_folders = backend.search(search_term, Folder)
    results_docs = backend.search(search_term, Page)

    qs_docs = BaseTreeNode.objects.filter(
        id__in=[
            p.document.basetreenode_ptr_id for p in results_docs
        ]
    )

    qs_docs = [
        node for node in qs_docs.all()
        if request.user.has_perm(Access.PERM_READ, node)
    ]

    # filter out all documents for which current user
    # does not has read access

    return render(
        request,
        "admin/search.html",
        {
            'results_docs': qs_docs,
            'results_folders': results_folders.results(),
            'search_term': search_term
        }
    )


@method_decorator(login_required, name='dispatch')
class AdminView(View):

    def get(self, request, id, **kwargs):
        entry = get_object_or_404(
            self.model, id=id
        )
        form = self.form_class(
            instance=entry
        )
        action_url = reverse(
            self.url, args=(id,)
        )

        return render(
            request,
            self.template_name,
            {
                'form': form,
                'action_url': action_url,
                'title': self.title
            }
        )


@method_decorator(login_required, name='dispatch')
class AdminListView(View):

    def render_with_pagination(self, request, page_number):
        objs = self.get_queryset(request)

        paginator = Paginator(objs, per_page=25)
        num_pages = paginator.num_pages
        page_obj = paginator.get_page(page_number)

        # 1.   Number of pages < 7: show all pages;
        # 2.   Current page <= 4: show first 7 pages;
        # 3.   Current page > 4 and < (number of pages - 4): show current page,
        #       3 before and 3 after;
        # 4.   Current page >= (number of pages - 4): show the last 7 pages.

        if num_pages <= 7 or page_number <= 4:  # case 1 and 2
            pages = [x for x in range(1, min(num_pages + 1, 7))]
        elif page_number > num_pages - 4:  # case 4
            pages = [x for x in range(num_pages - 6, num_pages + 1)]
        else:  # case 3
            pages = [x for x in range(page_number - 3, page_number + 4)]

        return render(
            request,
            self.template_name,
            {
                'object_list': page_obj.object_list,
                'pages': pages,
                'page_number': page_number,
                'page': page_obj
            }
        )

    def post(self, request, *args, **kwargs):
        selected_action = request.POST.getlist('_selected_action')
        go_action = request.POST['action']

        if go_action == 'delete_selected':
            deleted, row_count = self.model_class.objects.filter(
                id__in=selected_action
            ).delete()

            if deleted:
                count = row_count[self.model_label]

                if count == 1:
                    name = self.model_class._meta.verbose_name
                else:
                    name = self.model_class._meta.verbose_name_plural

                msg_sg = "%(count)s %(name)s was successfully deleted."
                msg_pl = "%(count)s %(name)s were successfully deleted."
                messages.info(
                    request,
                    ngettext(msg_sg, msg_pl, count) % {
                        'count': count,
                        'name': name
                    }
                )

        page_number = int(request.GET.get('page', 1))

        return self.render_with_pagination(
            request,
            page_number
        )

    def get(self, request, *args, **kwargs):
        page_number = int(request.GET.get('page', 1))

        return self.render_with_pagination(
            request,
            page_number
        )


class LogsListView(AdminListView):
    model_class = LogEntry
    model_label = 'admin.LogEntry'
    template_name = 'admin/log_entries.html'

    def get_queryset(self, request):
        if request.user.is_superuser:
            # superuser sees all logs
            return LogEntry.objects.all()

        logs = LogEntry.objects.filter(user=request.user)

        return logs


class TagsListView(AdminListView):
    model_class = Tag
    model_label = 'core.Tag'
    template_name = 'admin/tags.html'

    def get_queryset(self, request):
        return Tag.objects.filter(user=request.user)


class LogFormView(AdminView):
    model = LogEntry
    form_class = LogEntryForm
    url = 'admin:log'
    template_name = 'admin/log_entry.html'
    title = _('Log Entry')


class TagFormView(AdminView):
    model = Tag
    form_class = TagForm
    url = 'admin:tag'
    template_name = 'admin/tag.html'
    title = _('Tag')


@login_required
def tag_change_view(request, id):
    tag = get_object_or_404(Tag, id=id)

    action_url = reverse('admin:tag_change', args=(id,))
    form = TagForm(
        request.POST or None,
        instance=tag
    )

    if form.is_valid():
        form.save()
        return redirect("admin:tags")

    return render(
        request,
        'admin/tag.html',
        {
            'form': form,
            'action_url': action_url,
            'title': _('Edit Tag')
        }
    )
