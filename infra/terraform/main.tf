terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# Unique identifier variable for resources
variable "unique_id" {
  type    = string
  default = "de-unique-98213"
}

# 1. S3 Bucket & Versioning Configuration
resource "aws_s3_bucket" "platform_bucket" {
  bucket        = "document-platform-${var.unique_id}"
  force_destroy = true
}

resource "aws_s3_bucket_versioning" "bucket_versioning" {
  bucket = aws_s3_bucket.platform_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Folder Prefixes (Folders within the bucket)
resource "aws_s3_object" "folder_raw" {
  bucket = aws_s3_bucket.platform_bucket.id
  key    = "raw/"
}

resource "aws_s3_object" "folder_processed" {
  bucket = aws_s3_bucket.platform_bucket.id
  key    = "processed/"
}

resource "aws_s3_object" "folder_curated" {
  bucket = aws_s3_bucket.platform_bucket.id
  key    = "curated/"
}

resource "aws_s3_object" "folder_failed" {
  bucket = aws_s3_bucket.platform_bucket.id
  key    = "failed/"
}

# 2. RDS Postgres Instance Configuration
resource "aws_db_instance" "postgres_db" {
  identifier             = "document-platform-db"
  engine                 = "postgres"
  engine_version         = "15.4"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  db_name                = "document_platform"
  username               = "postgres"
  password               = "securepassword123" # In production, use dynamic secrets management
  publicly_accessible    = false
  skip_final_snapshot    = true
  apply_immediately      = true

  tags = {
    Environment = "Development"
    Project     = "Document Platform"
  }
}

# 3. IAM Role configuration with S3 & RDS Access
resource "aws_iam_role" "platform_role" {
  name = "document-platform-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

# IAM Policy for S3 access
resource "aws_iam_policy" "s3_access_policy" {
  name        = "document-platform-s3-access-policy"
  description = "Access policy for S3 bucket operations"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          aws_s3_bucket.platform_bucket.arn,
          "${aws_s3_bucket.platform_bucket.arn}/*"
        ]
      }
    ]
  })
}

# IAM Policy for RDS access
resource "aws_iam_policy" "rds_access_policy" {
  name        = "document-platform-rds-access-policy"
  description = "Access policy for RDS operations"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds-db:connect"
        ]
        Resource = [
          "arn:aws:rds-db:us-east-1:*:dbuser:${aws_db_instance.postgres_db.resource_id}/postgres"
        ]
      }
    ]
  })
}

# Attach S3 policy to IAM role
resource "aws_iam_role_policy_attachment" "attach_s3" {
  role       = aws_iam_role.platform_role.name
  policy_arn = aws_iam_policy.s3_access_policy.arn
}

# Attach RDS policy to IAM role
resource "aws_iam_role_policy_attachment" "attach_rds" {
  role       = aws_iam_role.platform_role.name
  policy_arn = aws_iam_policy.rds_access_policy.arn
}
