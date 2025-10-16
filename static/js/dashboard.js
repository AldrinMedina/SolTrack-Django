
// Auto-refresh ongoing contracts table every minute
if (window.location.pathname.includes('ongoing')) {
    setInterval(() => {
        fetch(window.location.href, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(res => res.text())
            .then(html => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newBody = doc.querySelector('tbody');
                document.querySelector('tbody').innerHTML = newBody.innerHTML;
            });
    }, 60000); // refresh every 60 seconds
}

// Mobile sidebar toggle
function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('show');
}

// Update timestamp
function updateTimestamp() {
    const now = new Date();
    document.getElementById('lastUpdated').textContent = now.toLocaleTimeString();
}

setInterval(updateTimestamp, 30000); // Update every 30 seconds

// Real-time temperature chart
const chartElement = document.getElementById('chartData');
const chartCanvas = document.getElementById('temperatureChart');

if (chartElement && chartCanvas) {
    const labels = JSON.parse(chartElement.dataset.labels);
    const values = JSON.parse(chartElement.dataset.values);

    const ctx = chartCanvas.getContext('2d');
    window.temperatureChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Temperature (°C)',
                data: values,
                borderColor: '#0d6efd',
                borderWidth: 2,
                fill: false,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    suggestedMin: -10,
                    suggestedMax: 10,
                    title: {
                        display: true,
                        text: 'Temperature (°C)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    }
                }
            }
        }
    });
}


// Performance chart
const performanceCtx = document.getElementById('performanceChart')?.getContext('2d');
if (performanceCtx) {
    new Chart(performanceCtx, {
        type: 'bar',
        data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'],
            datasets: [{
                label: 'Successful Deliveries',
                data: [45, 52, 48, 61, 55, 67, 43, 58, 62],
                backgroundColor: '#22c55e'
            }, {
                label: 'Temperature Breaches',
                data: [2, 1, 3, 1, 2, 1, 4, 2, 1],
                backgroundColor: '#ef4444'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top'
                }
            }
        }
    });
}

// Distribution chart
const distributionCtx = document.getElementById('distributionChart')?.getContext('2d');
if (distributionCtx) {
    new Chart(distributionCtx, {
        type: 'doughnut',
        data: {
            labels: ['Pfizer', 'Moderna', 'J&J', 'AstraZeneca', 'Sinovac'],
            datasets: [{
                data: [35, 25, 20, 12, 8],
                backgroundColor: [
                    '#6366f1',
                    '#8b5cf6',
                    '#06b6d4',
                    '#10b981',
                    '#f59e0b'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}



// Clear all alerts function
function clearAllAlerts() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        alert.style.opacity = '0.5';
        setTimeout(() => {
            alert.remove();
        }, 300);
    });
    
    // Update alert badge
    const alertBadge = document.querySelector('[data-tab="alerts"] .badge');
    if (alertBadge) {
        alertBadge.textContent = '0';
        alertBadge.className = 'badge bg-secondary ms-auto';
    }
}

// Add click handlers for action buttons
document.addEventListener('click', function(e) {
    
    if (e.target.closest('.btn-danger')) {
        alert('Initiating emergency call protocol...');
    }
    
    if (e.target.closest('.btn-warning')) {
        alert('Running diagnostic check on sensor...');
    }
});

document.addEventListener('DOMContentLoaded', function() {
    const productRadios = document.querySelectorAll('input[name="selected_product"]');
    const productNameInput = document.getElementById('product_name');
    const quantityInput = document.getElementById('quantity');
    const priceInput = document.getElementById('payment_amount');
    const sellerIdInput = document.getElementById('seller_id');

    productRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            const name = this.getAttribute('data-name');
            const qty = this.getAttribute('data-quantity');
            const price = this.getAttribute('data-price');
            const sellerId = this.getAttribute('data-seller');

            productNameInput.value = name;
            quantityInput.value = qty;
            priceInput.value = price;
            sellerIdInput.value = sellerId;
        });
    });
});

// Notification system
// function showNotification(message, type = 'info') {
//     const notification = document.createElement('div');
//     notification.className = `alert alert-${type} position-fixed`;
//     notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
//     notification.innerHTML = `
//         <div class="d-flex align-items-center">
//             <i class="bi bi-info-circle me-2"></i>
//             <span>${message}</span>
//             <button type="button" class="btn-close ms-auto" onclick="this.parentElement.parentElement.remove()"></button>
//         </div>
//     `;
//     document.body.appendChild(notification);
    
//     setTimeout(() => {
//         notification.remove();
//     }, 5000);
// }

// =====================
// 📊 Real-Time Dashboard Update
// =====================

function updateDashboard() {
    fetch(DASHBOARD_DATA_URL)  // <-- make sure this matches your Django URL name or pattern
        .then(response => response.json())
        .then(data => {
            // --- Overview Metrics ---
            if (document.getElementById("avgTemp")) {
                document.getElementById("avgTemp").textContent = `${data.avg_temp}°C`;
                document.getElementById("totalContracts").textContent = data.total_contracts;
                document.getElementById("contractBreakdown").textContent =
                    `${data.active_contracts} active, ${data.completed_contracts} completed`;
                document.getElementById("activeAlerts").textContent = data.active_alerts;
                document.getElementById("lastUpdated").textContent = new Date().toLocaleTimeString();
            }

            // --- Sidebar Badges ---
            const activeBadge = document.getElementById("activeBadge");
            const ongoingBadge = document.getElementById("ongoingBadge");
            const completedBadge = document.getElementById("completedBadge");
            const alertsBadge = document.getElementById("alertsBadge");
            if (activeBadge) activeBadge.textContent = data.active_contracts;
            if (ongoingBadge) ongoingBadge.textContent = data.ongoing_contracts;
            if (completedBadge) completedBadge.textContent = data.completed_contracts;
            if (alertsBadge) alertsBadge.textContent = data.active_alerts;

            // --- System Status ---
            const dot = document.getElementById("systemDot");
            const systemStatus = document.getElementById("systemStatus");
            if (dot && systemStatus) {
                dot.classList.remove("bg-success", "bg-danger");
                dot.classList.add(data.status_color);
                systemStatus.textContent = data.system_status;
            }

            // --- Temperature Chart ---
            const chartCanvas = document.getElementById("temperatureChart");
            if (window.temperatureChart && data.chart_labels && data.chart_values) {
                window.temperatureChart.data.labels = data.chart_labels;
                window.temperatureChart.data.datasets[0].data = data.chart_values;
                window.temperatureChart.update("none");
            }

        })
        .catch(err => console.error("Dashboard update failed:", err));
}

function updateOngoingShipments() {
    fetch(ONGOING_DATA_URL)
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(data => {
            const ongoingData = data.ongoing_data;
            const tableBody = document.querySelector('#ongoing-content table tbody');

            // Clear current rows
            tableBody.innerHTML = '';

            if (!ongoingData || ongoingData.length === 0) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="7" class="text-center text-muted py-3">
                            No ongoing shipments found.
                        </td>
                    </tr>
                `;
                return;
            }

            ongoingData.forEach(shipment => {
                const statusBadge = shipment.status === "In Transit"
                    ? `<span class="badge bg-info text-dark px-3 py-2 rounded-pill">${shipment.status}</span>`
                    : `<span class="badge bg-success px-3 py-2 rounded-pill">${shipment.status}</span>`;

                const temperatureDisplay = shipment.temperature
                    ? `<span class="fw-bold text-success">${shipment.temperature}</span>`
                    : `<span class="badge bg-secondary px-2 py-1">No Data</span>`;

                const newRow = `
                    <tr>
                        <td class="px-4 py-3">#${shipment.contract_id}</td>
                        <td class="px-4 py-3 fw-bold text-dark">${shipment.product_name}</td>
                        <td class="px-4 py-3">${temperatureDisplay}</td>
                        <td class="px-4 py-3">${statusBadge}</td>
                        <td class="px-4 py-3">${shipment.buyer_name || '—'}</td>
                        <td class="px-4 py-3">${shipment.seller_name || '—'}</td>
                        <td class="px-4 py-3">
                            <button class="btn btn-sm btn-outline-primary view-shipment" data-id="${shipment.contract_id}">
                                <i class="bi bi-eye"></i>
                            </button>
                        </td>
                    </tr>
                `;
                tableBody.insertAdjacentHTML('beforeend', newRow);
            });
        })
        .catch(error => console.error('Error fetching ongoing shipment data:', error));
}

// Auto-run for ongoing page
if (window.location.pathname.includes('ongoing')) {
    updateOngoingShipments();
    setInterval(updateOngoingShipments, 10000); // 10 seconds
}

document.addEventListener('click', function(e) {
    const button = e.target.closest('.view-shipment');
    if (button) {
        const id = button.dataset.id;

        fetch(SHIPMENT_DETAILS_URL.replace('0', id))
            .then(res => {
                if (!res.ok) throw new Error('Failed to fetch shipment details');
                return res.json();
            })
            .then(data => {
                document.getElementById('shipmentDetails').innerHTML = `
                    <p><strong>Shipment ID:</strong> #${data.contract_id}</p>
                    <p><strong>Product:</strong> ${data.product_name}</p>
                    <p><strong>Quantity:</strong> ${data.quantity}</p>
                    <p><strong>Status:</strong> ${data.status}</p>
                    <p><strong>Temperature:</strong> ${data.latest_temp}°C</p>
                    <hr>
                    <h6>Buyer Information</h6>
                    <p><strong>Name:</strong> ${data.buyer_name}<br>
                       <strong>Email:</strong> ${data.buyer_email}<br>
                       <strong>Wallet:</strong> ${data.buyer_wallet}</p>
                    <h6>Seller Information</h6>
                    <p><strong>Name:</strong> ${data.seller_name}<br>
                       <strong>Email:</strong> ${data.seller_email}<br>
                       <strong>Wallet:</strong> ${data.seller_wallet}</p>
                    <hr>
                    <small class="text-muted">Last Recorded: ${data.recorded_at}</small>
                `;

                const modal = new bootstrap.Modal(document.getElementById('shipmentModal'));
                modal.show();
            })
            .catch(err => console.error(err));
    }
});



// Auto-refresh alerts section every minute
setInterval(() => {
    fetch('/dashboard/alerts/')
        .then(response => response.text())
        .then(html => {
            const parser = new DOMParser();
            const newContent = parser.parseFromString(html, 'text/html')
                .querySelector('#alerts-content');
            document.querySelector('#alerts-content').innerHTML = newContent.innerHTML;
        })
        .catch(err => console.error('Alert refresh failed:', err));
}, 60000);


// Auto-refresh only if dashboard-related pages are active
if (window.location.pathname.includes("overview") || 
    window.location.pathname.includes("dashboard")) {
    setInterval(updateDashboard, 30000); // every 30 sec
    updateDashboard(); // run immediately on load
}

