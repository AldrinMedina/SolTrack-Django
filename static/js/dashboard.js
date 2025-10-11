
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
    // 1. Fetch data from the new JSON endpoint
    fetch('/ongoing/data/')// Using the correct URL from urls.py
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            const ongoingData = data.ongoing_data;
        const tableBody = document.querySelector('#ongoing-content table tbody');

        // --- CRITICAL FIX 1: CLEAR THE TABLE BODY ---
        tableBody.innerHTML = ''; 
            // A more efficient way: update only the relevant cells if the row exists.
            // However, since your template does a full re-render, we'll fix 
            // the rendering logic to correctly match the HTML structure.
            
            tableBody.innerHTML = ''; // Clear existing rows

            if (ongoingData.length === 0) {
                // Display the 'No shipments found' message
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="7" class="text-center text-muted py-3">
                            No ongoing shipments found.
                        </td>
                    </tr>
                `;
                return;
            }

        // 3. Re-render the rows with fresh data
        ongoingData.forEach(shipment => {
        const statusClass = shipment.status === "In Transit" ? 'bg-info text-dark' : 'bg-success';
        // --- CRITICAL FIX 2: Add a check for temperature ---
        const displayTemperature = shipment.temperature || 'N/A';
    
        const newRow = `
            <tr>
                <td class="fw-medium">#${shipment.contract_id}</td>
                <td>${shipment.product_name}</td>
                <td>${displayTemperature}</td> 
                <td>
                    <span class="badge ${statusClass}">${shipment.status}</span>
                </td>
                <td>${shipment.buyer_name || '—'}</td>  <td>${shipment.seller_name || '—'}</td> <td>
                    <button class="btn btn-sm btn-outline-primary">
                        <i class="bi bi-eye"></i>
                    </button>
                </td>
            </tr>
        `;
        tableBody.insertAdjacentHTML('beforeend', newRow);
        });
    })
    .catch(error => {
        console.error('Error fetching ongoing shipment data:', error);
    });
}

if (window.location.pathname.includes('ongoing')) {
    // Run the update function immediately on page load
    updateOngoingShipments(); 

    // Set the interval to run the update function every 60 seconds (60000 milliseconds)
    setInterval(updateOngoingShipments, 10000); 
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


// Auto-refresh only if dashboard-related pages are active
if (window.location.pathname.includes("overview") || 
    window.location.pathname.includes("dashboard")) {
    setInterval(updateDashboard, 30000); // every 30 sec
    updateDashboard(); // run immediately on load
}

