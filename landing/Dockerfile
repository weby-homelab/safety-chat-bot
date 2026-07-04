FROM nginx:alpine

# Copy static website files to nginx html directory
COPY index.html /usr/share/nginx/html/index.html
COPY favicon.svg /usr/share/nginx/html/favicon.svg

# Expose port 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
