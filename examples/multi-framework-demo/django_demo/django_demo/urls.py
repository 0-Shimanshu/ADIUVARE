from django.urls import path

from demo.views import hard_stop, health, protected, public, review

urlpatterns = [
    path("", health, name="health"),
    path("public/", public, name="public"),
    path("protected/", protected, name="protected"),
    path("review/", review, name="review"),
    path("hard-stop/", hard_stop, name="hard_stop"),
]
