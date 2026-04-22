-- CMP-51: Replace Tistory columns with WordPress columns in blog_posts

BEGIN;

ALTER TABLE blog_posts
  RENAME COLUMN tistory_post_id TO wordpress_post_id;

ALTER TABLE blog_posts
  RENAME COLUMN tistory_url TO wordpress_url;

COMMIT;
