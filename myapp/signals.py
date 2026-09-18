from django.db.models.signals import post_delete
from django.dispatch import receiver

from myapp.models import Post
from myapp.views.post import delete_post_vectors

#Post が削除された直後にこの関数を実行する
@receiver(post_delete, sender=Post)
# post_delete: モデル削除後に発火するイベント
# sender=Post: Post が削除された時だけ反応する
# instance: 削除された投稿データ
def delete_post_vectors_on_post_delete(sender, instance, **kwargs):
    try:
        delete_post_vectors(instance.id)
    except Exception:
        pass