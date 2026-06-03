# LinkedIn-Style Website Storage Brainstorm

## Project Idea

The idea is to build a simple LinkedIn-style website where users can create a professional profile, upload their photo, share posts, upload resumes, and apply for jobs.

For this type of website, we need a place to store files uploaded by users. These files can include profile pictures, resume PDFs, certificates, post images, company logos, and banner images.

## Features We Can Implement

### Profile Features

- User signup and login
- Create and edit profile
- Upload profile photo
- Upload profile banner
- Add skills, education, and work experience
- Upload resume
- Upload certificates

### Post Features

- Create text posts
- Upload image with a post
- Like posts
- Comment on posts
- View posts from other users

### Job Features

- Create company profile
- Upload company logo
- Post job openings
- Search jobs
- Apply for jobs using uploaded resume

### Storage Features

- Store profile photos
- Store post images
- Store resumes
- Store certificates
- Store company logos
- Keep private documents secure
- Show public images directly on the website

## Why Cloud Storage Is Needed

Files like photos and resumes can become large. If we store them inside the database, the database can become slow and difficult to manage. Cloud storage is better because it is made for storing files.

## Option 1: Amazon S3

Amazon S3 is a storage service from AWS. It is used to store files such as images, documents, videos, and backups.

### Good Points

- Very popular for web applications
- Many tutorials and examples are available
- Easy to use with backend applications
- Supports public and private files
- Can create temporary secure links for private files
- Good choice for storing images and resumes

### Challenges

- Permissions need to be set carefully
- We should not make private files public by mistake

## Option 2: Azure Blob Storage

Azure Blob Storage is a storage service from Microsoft Azure. It can also store images, documents, videos, and other files.

### Good Points

- Good option if the project already uses Azure
- Works well with Microsoft services
- Supports public and private files
- Can create secure temporary links
- Good for company or enterprise projects

### Challenges

- Better choice when the full project is already built on Azure

## Final Choice

For this project, I would choose **Amazon S3**.

The main reason is that Amazon S3 is widely used, and very suitable for storing user-uploaded files like profile photos, resumes, certificates, and post images.
Also it has better CDN network which will be faster compare to Azure blob storage.

Azure Blob Storage is also a good service, but I would choose it mainly if the whole project was already using Microsoft Azure. Since this is a learning project and we want something easy to explain and implement, Amazon S3 is the better choice.

## Public and Private Files

Some files can be public because everyone should see them. Some files should be private because they contain personal information.

| File | Access |
|---|---|
| Profile photo | Public |
| Banner image | Public |
| Post image | Public |
| Company logo | Public |
| Resume | Private |
| Certificate | Private or restricted |
