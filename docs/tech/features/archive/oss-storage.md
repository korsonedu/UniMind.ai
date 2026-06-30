# OSS 存储集成

## 概述

UniMind 使用阿里云 OSS 作为文件存储服务。视频文件通过 OSS 原生分片上传直传 OSS（不经过后端带宽），其他小文件通过后端中转写入 OSS。

## 上传策略

| 文件类型 | 上传路径 | 后端角色 |
|---------|---------|---------|
| 课程视频 (video_file) | OSS 分片直传 | 签名 + 确认 + 创建课程 |
| 课程封面/课件/参考资料 | FormData POST 后端 | 接收文件写入 OSS |
| 其他（考试/文章/答疑/Logo 等） | FormData POST 后端 | 接收文件写入 OSS |

## 架构

```
视频上传（OSS 分片直传）：
  前端 → POST /oss/multipart/init（拿签名 URL 列表）
       → 并发 PUT 各片直传 OSS（3 并发，每片 10MB，自动重试）
       → POST /oss/multipart/complete（元数据 + 其他文件 + parts ETag）
         → 后端合并分片 → 创建课程 → 扣配额 → 触发 ASR

小文件上传（后端中转）：
  前端 → FormData POST /courses/（或其他 CRUD 端点）
       → 后端校验 + 写入 OSS
```

## 多租户文件隔离

文件路径按机构 ID 隔离：
```
institutions/{institution_id}/video/{uuid}.mp4
institutions/{institution_id}/cover/{uuid}.jpg
```

## API 接口

### 初始化分片上传

**POST** `/api/courses/oss/multipart/init/`

**请求：**
```json
{
  "file_name": "video.mp4",
  "file_size": 104857600
}
```

**响应：**
```json
{
  "upload_id": "abc123...",
  "object_key": "institutions/123/video/uuid.mp4",
  "part_size": 10485760,
  "total_parts": 10,
  "signed_urls": ["https://oss...?uploadId=...&partNumber=1", "..."]
}
```

### 确认分片完成 + 创建课程

**POST** `/api/courses/oss/multipart/complete/`

**请求（FormData）：**
```
upload_id: "abc123..."
object_key: "institutions/123/video/uuid.mp4"
parts: [{"number": 1, "etag": "\"xxx\""}, ...]
title: "课程标题"
description: "描述"
elo_reward: 50
cover_image: (File)
courseware: (File)
```

**响应：** CourseSerializer 序列化的课程数据（201）

## 权限控制

- `IsAdmin` + `HasQuota`：仅机构管理员可上传
- 租户只能操作自己机构路径下的文件
- 超管可访问所有文件

## 环境变量

```bash
OSS_ACCESS_KEY_ID=xxx
OSS_ACCESS_KEY_SECRET=xxx
OSS_BUCKET_NAME=unimind-courses
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
```

## 文件访问

媒体文件通过 `media_serve` 视图服务，支持 HTTP Range（视频 seek）、304 缓存、租户权限校验。配置 OSS 时自动重定向到签名 URL。
