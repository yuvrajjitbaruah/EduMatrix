from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect


def retired_feature_redirect(request, feature_name, redirect_to='dashboard_home', extra_message=''):
    message = f'{feature_name} has been retired from this EduMatrix build.'
    if extra_message:
        message = f'{message} {extra_message}'
    messages.info(request, message)
    return redirect(redirect_to)


def retired_feature_json(feature_name, extra_message=''):
    message = f'{feature_name} has been retired from this EduMatrix build.'
    if extra_message:
        message = f'{message} {extra_message}'
    return JsonResponse({'success': False, 'error': message}, status=410)
