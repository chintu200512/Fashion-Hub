// ============================================
// CART MANAGEMENT
// ============================================

/**
 * Add product to cart
 * @param {string} productId - The product ID to add
 */
async function addToCart(productId) {
    if (!productId) {
        showNotification('Invalid product', 'danger');
        return;
    }

    try {
        const res = await fetch("/api/cart/add", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                product_id: productId,
                quantity: 1
            })
        });

        const data = await res.json();

        if (data.success) {
            showNotification('Added to cart successfully!', 'success');
            updateCartCount(); // Update cart badge
        } else {
            showNotification(data.message || 'Failed to add to cart', 'danger');
        }
    } catch (error) {
        console.error('Error adding to cart:', error);
        showNotification('Error adding to cart', 'danger');
    }
}

/**
 * Remove product from cart
 * @param {string} productId - The product ID to remove
 */
async function removeFromCart(productId) {
    if (!productId) return;

    if (!confirm('Remove this item from cart?')) return;

    try {
        const res = await fetch(`/api/cart/remove/${productId}`, {
            method: "DELETE"
        });

        const data = await res.json();

        if (data.success) {
            showNotification('Removed from cart', 'success');
            location.reload(); // Refresh cart page
        } else {
            showNotification(data.message || 'Failed to remove', 'danger');
        }
    } catch (error) {
        console.error('Error removing from cart:', error);
        showNotification('Error removing from cart', 'danger');
    }
}

/**
 * Update cart item quantity
 * @param {string} productId - The product ID
 * @param {number} quantity - New quantity
 */
async function updateCartQuantity(productId, quantity) {
    if (!productId) return;

    try {
        const res = await fetch("/api/cart/update", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                product_id: productId,
                quantity: parseInt(quantity)
            })
        });

        const data = await res.json();

        if (data.success) {
            updateCartCount();
            // Update subtotal and total on cart page
            if (typeof updateCartTotals === 'function') {
                updateCartTotals();
            } else {
                location.reload();
            }
        } else {
            showNotification(data.message || 'Failed to update', 'danger');
        }
    } catch (error) {
        console.error('Error updating cart:', error);
        showNotification('Error updating cart', 'danger');
    }
}

/**
 * Update cart count badge in navbar
 */
async function updateCartCount() {
    try {
        const res = await fetch("/api/cart");
        const data = await res.json();
        
        const cartCount = data.items?.reduce((sum, item) => sum + item.quantity, 0) || 0;
        const cartBadge = document.getElementById('cartCount');
        
        if (cartBadge) {
            cartBadge.innerText = cartCount;
        }
    } catch (error) {
        console.error('Error updating cart count:', error);
    }
}

/**
 * Get user's cart
 * @returns {Promise<Object>} Cart data
 */
async function getCart() {
    try {
        const res = await fetch("/api/cart");
        const data = await res.json();
        return data;
    } catch (error) {
        console.error('Error fetching cart:', error);
        return { items: [], total: 0 };
    }
}

// ============================================
// ORDER MANAGEMENT
// ============================================

/**
 * Place order - redirect to order page
 * @param {string} productId - The product ID to order
 */
function placeOrder(productId) {
    if (!productId) {
        showNotification('Invalid product', 'danger');
        return;
    }
    
    // Redirect to order form
    window.location.href = `/buy/product/${productId}`;
}

/**
 * Submit order from order form
 * @param {Object} orderData - Order data
 * @returns {Promise<boolean>} Success status
 */
async function submitOrder(orderData) {
    try {
        const response = await axios.post('/place-order', orderData);
        
        if (response.data.success) {
            showNotification('Order placed successfully!', 'success');
            setTimeout(() => {
                window.location.href = '/orders';
            }, 2000);
            return true;
        } else {
            showNotification(response.data.message || 'Order failed', 'danger');
            return false;
        }
    } catch (error) {
        const message = error.response?.data?.message || 'Error placing order';
        showNotification(message, 'danger');
        return false;
    }
}

/**
 * Get order details
 * @param {string} orderId - The order ID
 * @returns {Promise<Object|null>} Order details
 */
async function getOrderDetails(orderId) {
    try {
        const response = await axios.get(`/order/${orderId}`);
        return response.data;
    } catch (error) {
        console.error('Error fetching order:', error);
        return null;
    }
}

/**
 * Cancel order (only if pending)
 * @param {string} orderId - The order ID to cancel
 * @returns {Promise<boolean>} Success status
 */
async function cancelOrder(orderId) {
    if (!confirm('Are you sure you want to cancel this order?')) {
        return false;
    }
    
    try {
        const response = await axios.post(`/api/order/update-status/${orderId}`, {
            status: 'cancelled'
        });
        
        if (response.data.success) {
            showNotification('Order cancelled successfully', 'success');
            setTimeout(() => location.reload(), 1500);
            return true;
        } else {
            showNotification(response.data.message, 'danger');
            return false;
        }
    } catch (error) {
        showNotification('Error cancelling order', 'danger');
        return false;
    }
}

/**
 * Update order status (for admin)
 * @param {string} orderId - The order ID
 * @param {string} status - New status (pending, confirmed, shipped, delivered)
 * @returns {Promise<boolean>} Success status
 */
async function updateOrderStatus(orderId, status) {
    try {
        const response = await axios.post(`/api/order/update-status/${orderId}`, {
            status: status
        });
        
        if (response.data.success) {
            showNotification(`Order status updated to ${status}`, 'success');
            setTimeout(() => location.reload(), 1000);
            return true;
        } else {
            showNotification(response.data.message, 'danger');
            return false;
        }
    } catch (error) {
        showNotification('Error updating order status', 'danger');
        return false;
    }
}

// ============================================
// WISHLIST MANAGEMENT
// ============================================

/**
 * Toggle wishlist item
 * @param {string} productId - The product ID
 */
async function toggleWishlist(productId) {
    if (!productId) return;

    try {
        const response = await axios.post('/api/wishlist/toggle', { 
            product_id: productId 
        });
        
        if (response.data.success) {
            const btn = event?.currentTarget;
            const icon = btn?.querySelector('i');
            
            if (response.data.action === 'added') {
                if (icon) {
                    icon.classList.remove('far');
                    icon.classList.add('fas');
                    btn?.classList.add('active');
                }
                showNotification('Added to wishlist!', 'success');
            } else {
                if (icon) {
                    icon.classList.remove('fas');
                    icon.classList.add('far');
                    btn?.classList.remove('active');
                }
                showNotification('Removed from wishlist', 'info');
            }
            updateWishlistCount();
        }
    } catch (error) {
        if (error.response?.status === 401) {
            showNotification('Please login to add to wishlist', 'warning');
            setTimeout(() => {
                window.location.href = '/login';
            }, 1500);
        } else {
            showNotification('Failed to update wishlist', 'danger');
        }
    }
}

/**
 * Update wishlist count badge
 */
async function updateWishlistCount() {
    try {
        const response = await axios.get('/api/wishlist');
        const count = response.data.length || 0;
        const wishlistBadge = document.getElementById('wishlistCount');
        
        if (wishlistBadge) {
            wishlistBadge.innerText = count;
        }
    } catch (error) {
        console.error('Error updating wishlist count:', error);
    }
}

// ============================================
// NOTIFICATION SYSTEM
// ============================================

/**
 * Show toast notification
 * @param {string} message - Notification message
 * @param {string} type - Notification type (success, danger, warning, info)
 */
function showNotification(message, type = 'success') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 80px; right: 20px; z-index: 9999; min-width: 250px; animation: slideIn 0.3s ease;';
    
    // Set icon based on type
    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    if (type === 'danger') icon = 'fa-exclamation-circle';
    if (type === 'warning') icon = 'fa-exclamation-triangle';
    
    notification.innerHTML = `
        <i class="fas ${icon} me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto remove after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

/**
 * Format price in Indian Rupees
 * @param {number} price - Price to format
 * @returns {string} Formatted price
 */
function formatPrice(price) {
    return new Intl.NumberFormat('en-IN').format(price);
}

/**
 * Validate mobile number (10 digits)
 * @param {string} mobile - Mobile number to validate
 * @returns {boolean} Is valid
 */
function isValidMobile(mobile) {
    return /^\d{10}$/.test(mobile);
}

/**
 * Validate email format
 * @param {string} email - Email to validate
 * @returns {boolean} Is valid
 */
function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// ============================================
// INITIALIZATION
// ============================================

// Update cart and wishlist counts on page load
document.addEventListener('DOMContentLoaded', function() {
    updateCartCount();
    updateWishlistCount();
    
    // Add CSS animation for notifications if not present
    if (!document.querySelector('#notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            @keyframes slideIn {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
        `;
        document.head.appendChild(style);
    }
});