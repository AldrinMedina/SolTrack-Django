
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
const ctx = document.getElementById('temperatureChart')?.getContext('2d');
if (ctx) {
    const temperatureChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['12:00', '12:30', '13:00', '13:30', '14:00', '14:30', '15:00'],
            datasets: [{
                label: 'Sensor #001',
                data: [-1.2, -1.1, -1.3, -1.0, -1.2, -1.4, -1.2],
                borderColor: '#22c55e',
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                tension: 0.4
            }, {
                label: 'Sensor #002',
                data: [-8.1, -7.9, -8.2, -8.0, -8.1, -8.3, -8.1],
                borderColor: '#f59e0b',
                backgroundColor: 'rgba(245, 158, 11, 0.1)',
                tension: 0.4
            }, {
                label: 'Sensor #003',
                data: [-2.8, -2.7, -2.9, -2.6, -2.8, -3.0, -2.8],
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                tension: 0.4
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

    // Simulate real-time updates
    setInterval(() => {
        const datasets = temperatureChart.data.datasets;
        datasets.forEach(dataset => {
            // Add new random temperature reading
            const lastValue = dataset.data[dataset.data.length - 1];
            const newValue = lastValue + (Math.random() - 0.5) * 0.5;
            dataset.data.push(newValue);
            
            // Keep only last 10 data points
            if (dataset.data.length > 10) {
                dataset.data.shift();
            }
        });
        
        // Update labels
        const now = new Date();
        const timeLabel = now.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        temperatureChart.data.labels.push(timeLabel);
        if (temperatureChart.data.labels.length > 10) {
            temperatureChart.data.labels.shift();
        }
        
        temperatureChart.update('none');
    }, 5000); // Update every 5 seconds
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

// Simulate real-time temperature updates
// function updateSensorReadings() {
//     const sensors = document.querySelectorAll('[data-sensor]');
//     sensors.forEach(sensor => {
//         const currentTemp = parseFloat(sensor.textContent);
//         const variation = (Math.random() - 0.5) * 0.3;
//         const newTemp = (currentTemp + variation).toFixed(1);
//         sensor.textContent = newTemp + '°C';
        
//         // Update status based on temperature
//         const statusBadge = sensor.parentNode.querySelector('.badge');
//         if (parseFloat(newTemp) < -8 || parseFloat(newTemp) > 2) {
//             statusBadge.className = 'badge status-critical';
//             statusBadge.innerHTML = '<i class="bi bi-exclamation-triangle me-1"></i>Critical';
//         } else if (parseFloat(newTemp) < -6 || parseFloat(newTemp) > 0) {
//             statusBadge.className = 'badge status-warning';
//             statusBadge.innerHTML = '<i class="bi bi-exclamation-circle me-1"></i>Warning';
//         } else {
//             statusBadge.className = 'badge status-normal';
//             statusBadge.innerHTML = '<i class="bi bi-check-circle me-1"></i>Normal';
//         }
//     });
// }

// Update sensor readings every 10 seconds
setInterval(updateSensorReadings, 10000);

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
    if (e.target.closest('.btn-outline-primary')) {
        alert('Opening detailed monitoring view...');
    }
    
    if (e.target.closest('.btn-danger')) {
        alert('Initiating emergency call protocol...');
    }
    
    if (e.target.closest('.btn-warning')) {
        alert('Running diagnostic check on sensor...');
    }
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
    fetch("/dashboard/data/")  // <-- make sure this matches your Django URL name or pattern
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
            if (chartCanvas && window.temperatureChart) {
                window.temperatureChart.data.labels = data.chart_labels;
                window.temperatureChart.data.datasets[0].data = data.chart_values;
                window.temperatureChart.update();
            }
        })
        .catch(err => console.error("Dashboard update failed:", err));
}

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


// Auto-refresh every 30 seconds
setInterval(updateDashboard, 30000);
