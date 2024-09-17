FROM php:8.2-fpm-alpine

# Install system dependencies
RUN apk add --no-cache \
    icu-dev \
    ffmpeg \
    python3 \
    py3-pip

# Install PHP extensions
RUN docker-php-ext-install pdo pdo_mysql \
    && docker-php-ext-configure intl \
    && docker-php-ext-install intl \
    && docker-php-ext-enable intl

# Install yt-dlp in a virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip3 install --no-cache-dir yt-dlp

# Install Composer
COPY --from=composer:latest /usr/bin/composer /usr/local/bin/composer

# Set working directory
WORKDIR /var/www/html

# Switch to www-data user
USER www-data

# Expose port 9000 and start php-fpm server
EXPOSE 9000
CMD ["php-fpm"]