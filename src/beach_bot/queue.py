from dataclasses import dataclass

@dataclass
class Video:
    id:str
    url:str
    title:str
    data:any

class Queue:
    videos:list[Video] = []

    @classmethod
    def has(cls, video:Video):
        return any([v for v in cls.videos if v.id == video.id])

    @classmethod
    def pop(cls):
        return cls.videos.pop(0)

    @classmethod
    def reset(cls):
        cls.videos = []