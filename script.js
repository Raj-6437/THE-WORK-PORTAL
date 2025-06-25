document.addEventListener('DOMContentLoaded', function() {
    // Sample freelancer data
    const freelancers = [
        {
            name: "Mia Turner",
            location: "Germany",
            skills: "Webflow Developer | UI Designer",
            email: "mia.turner@gmail.com"
        },
        {
            name: "Leo Cohen",
            location: "Australia",
            skills: "Graphic Designer",
            email: "leo.cohen@gmail.com"
        },
        {
            name: "Zoe Chase",
            location: "Australia",
            skills: "Low Code | Webflow Developer",
            email: "hello@zoechase.com"
        },
        {
            name: "Oliver Davis",
            location: "Germany",
            skills: "Senior Researcher | UI Designer",
            email: "welcome@designdavis.com"
        },
        {
            name: "Ava Wells",
            location: "Brazil",
            skills: "Senior UX Designer",
            email: "ava-wells@gmail.com"
        },
        {
            name: "John Smith",
            location: "Singapore",
            skills: "Design Systems",
            email: "info@johnsmith.com"
        }
    ];

    const freelancersList = document.getElementById('freelancers-list');
    const searchInput = document.getElementById('freelancer-search');
    const searchBtn = document.getElementById('search-btn');
    const locationFilter = document.getElementById('location-filter');
    const skillFilter = document.getElementById('skill-filter');

    // Display all freelancers initially
    displayFreelancers(freelancers);

    // Search functionality
    searchBtn.addEventListener('click', filterFreelancers);
    searchInput.addEventListener('keyup', function(e) {
        if (e.key === 'Enter') {
            filterFreelancers();
        }
    });

    // Filter functionality
    locationFilter.addEventListener('change', filterFreelancers);
    skillFilter.addEventListener('change', filterFreelancers);

    function filterFreelancers() {
        const searchTerm = searchInput.value.toLowerCase();
        const location = locationFilter.value;
        const skill = skillFilter.value;

        const filtered = freelancers.filter(freelancer => {
            const matchesSearch = freelancer.name.toLowerCase().includes(searchTerm) || 
                                freelancer.skills.toLowerCase().includes(searchTerm) ||
                                freelancer.email.toLowerCase().includes(searchTerm);
            
            const matchesLocation = location === '' || freelancer.location === location;
            const matchesSkill = skill === '' || freelancer.skills.includes(skill);
            
            return matchesSearch && matchesLocation && matchesSkill;
        });

        displayFreelancers(filtered);
    }

    function displayFreelancers(freelancersToDisplay) {
        freelancersList.innerHTML = '';

        if (freelancersToDisplay.length === 0) {
            freelancersList.innerHTML = '<p class="no-results">No freelancers found matching your criteria.</p>';
            return;
        }

        freelancersToDisplay.forEach(freelancer => {
            const card = document.createElement('div');
            card.className = 'freelancer-card';
            
            card.innerHTML = `
                <div class="freelancer-header">
                    <div>
                        <h3 class="freelancer-name">${freelancer.name}</h3>
                        <p class="freelancer-location">${freelancer.location}</p>
                    </div>
                </div>
                <p class="freelancer-skills">${freelancer.skills}</p>
                <p class="freelancer-email">${freelancer.email}</p>
                <div class="freelancer-actions">
                    <button class="btn btn-primary">Hire</button>
                    <button class="btn btn-outline">Message</button>
                </div>
            `;
            
            freelancersList.appendChild(card);
        });
    }

    // Notification count animation
    const notificationCount = document.querySelector('.notification-count');
    if (notificationCount) {
        setInterval(() => {
            notificationCount.style.transform = 'scale(1.2)';
            setTimeout(() => {
                notificationCount.style.transform = 'scale(1)';
            }, 300);
        }, 5000);
    }

    // Open chat modal
    function openChatModal(partnerName, workId) {
      document.getElementById('partner-name').textContent = partnerName;
      document.getElementById('chat-modal').style.display = 'block';
      
      if (workId) {
        fetch(`/get_work_details/${workId}`)
          .then(response => response.json())
          .then(work => {
            const details = document.getElementById('project-details-chat');
            if (work && !work.error) {
              details.innerHTML = `
                <p><strong>Project:</strong> ${work.title}</p>
                ${work.budget ? `<p><strong>Budget:</strong> $${work.budget}</p>` : ''}
              `;
            }
          });
      }
    }

    // Close chat modal
    function closeChatModal() {
      document.getElementById('chat-modal').style.display = 'none';
    }

    // Send message
    document.getElementById('send-btn').addEventListener('click', sendMessage);
    document.getElementById('message-text').addEventListener('keypress', e => {
      if (e.key === 'Enter') sendMessage();
    });

    function sendMessage() {
      const messageInput = document.getElementById('message-text');
      const message = messageInput.value.trim();
      
      if (message && currentBidId) {
        // In a real implementation, you would send this via Socket.IO
        addMessageToChat({
          message: message,
          sender_id: {{ session['user_id'] }},
          profile_photo: "{{ user['profile_photo'] }}",
          timestamp: new Date().toLocaleTimeString()
        }, true);
        
        messageInput.value = '';
      }
    }

    // Add message to UI
    function addMessageToChat(msg, isSent = false) {
      const container = document.getElementById('chat-messages');
      const messageElement = document.createElement('div');
      
      messageElement.className = `message ${isSent ? 'sent' : 'received'}`;
      messageElement.innerHTML = `
        <div class="message-content">${msg.message}</div>
        <div class="message-time">${msg.timestamp}</div>
      `;
      
      container.appendChild(messageElement);
      container.scrollTop = container.scrollHeight;
    }

    // Accept bid
    function acceptBid(bidId, workId) {
      fetch(`/get_bid_details/${bidId}`)
        .then(response => response.json())
        .then(bid => {
          const modalContent = `
            <h3>Accept Bid from ${bid.username}</h3>
            <p>Amount: $${bid.amount}</p>
            <p>Message: ${bid.message || 'No message'}</p>
            <button class="btn btn-primary" onclick="confirmBid(${bidId})">Confirm Acceptance</button>
          `;
          document.getElementById('bid-details-content').innerHTML = modalContent;
          document.getElementById('bid-details-modal').style.display = 'block';
        });
    }

    // Confirm bid acceptance
    function confirmBid(bidId) {
      fetch('/confirm_bid', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ bid_id: bidId })
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          alert('Bid accepted successfully!');
          closeBidModal();
          // Refresh bids section
          loadBids();
        }
      });
    }
});