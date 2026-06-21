"""Collection of all mixins for the Instagram Private API client"""
from .account import AccountMixin
from .auth import AuthMixin
from .clips import ClipsMixin
from .collection import CollectionMixin
from .comment import CommentMixin
from .direct import DirectMixin
from .feed import FeedMixin
from .friendship import FriendshipMixin
from .hashtag import HashtagMixin
from .insights import InsightsMixin
from .live import LiveMixin
from .location import LocationMixin
from .media import MediaMixin
from .notification import NotificationMixin
from .private import PrivateRequestMixin
from .search import SearchMixin
from .story import StoryMixin
from .upload import UploadMixin
from .user import UserMixin

__all__ = [
    "AccountMixin",
    "AuthMixin",
    "ClipsMixin",
    "CollectionMixin",
    "CommentMixin",
    "DirectMixin",
    "FeedMixin",
    "FriendshipMixin",
    "HashtagMixin",
    "InsightsMixin",
    "LiveMixin",
    "LocationMixin",
    "MediaMixin",
    "NotificationMixin",
    "PrivateRequestMixin",
    "SearchMixin",
    "StoryMixin",
    "UploadMixin",
    "UserMixin",
]
