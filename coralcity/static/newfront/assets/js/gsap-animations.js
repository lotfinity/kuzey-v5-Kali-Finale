(function () {
  'use strict';

  if (typeof gsap === 'undefined') return;

  gsap.registerPlugin(ScrollTrigger);

  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    gsap.set('[data-gsap]', { clearProps: 'all' });
    return;
  }

  var mm = gsap.matchMedia();

  // --- Banner hero entrance ---
  function animateBannerSlide(slide) {
    if (!slide) return;
    var category = slide.querySelector('.category');
    var headingSpans = slide.querySelectorAll('h2 span');
    var tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
    if (category) {
      tl.fromTo(category, { y: 30, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6 });
    }
    if (headingSpans.length) {
      tl.fromTo(headingSpans, { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.8, stagger: 0.25 }, '-=0.3');
    }
  }

  var activeSlide = document.querySelector('.main-banner .owl-item.active .item, .main-banner .item-1');
  if (activeSlide) animateBannerSlide(activeSlide);

  var owlBanner = document.querySelector('.owl-banner');
  if (owlBanner) {
    owlBanner.addEventListener('translated.owl.carousel', function () {
      var current = document.querySelector('.main-banner .owl-item.active .item');
      if (current) {
        gsap.set([current.querySelector('.category'), current.querySelectorAll('h2 span')], { clearProps: 'all' });
        requestAnimationFrame(function () { animateBannerSlide(current); });
      }
    });
  }

  // --- Scroll animations ---

  // Desktop
  mm.add('(min-width: 768px)', function () {

    // Featured
    var featured = document.querySelector('.featured');
    if (featured) {
      var leftImg = featured.querySelector('.left-image');
      if (leftImg) {
        gsap.fromTo(leftImg, { x: -80, opacity: 0 }, {
          x: 0, opacity: 1, duration: 1, ease: 'power3.out',
          scrollTrigger: { trigger: featured, start: 'top 80%' }
        });
      }
      var heading = featured.querySelector('.section-heading');
      if (heading) {
        gsap.fromTo(heading, { y: 50, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.8, ease: 'power3.out',
          scrollTrigger: { trigger: heading, start: 'top 80%' }
        });
      }
      var accordionItems = featured.querySelectorAll('.accordion-item');
      if (accordionItems.length) {
        gsap.fromTo(accordionItems, { y: 40, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.6, stagger: 0.15, ease: 'power3.out',
          scrollTrigger: { trigger: '.accordion', start: 'top 80%' }
        });
      }
      var infoItems = featured.querySelectorAll('.info-table li');
      if (infoItems.length) {
        gsap.fromTo(infoItems, { x: 60, opacity: 0 }, {
          x: 0, opacity: 1, duration: 0.6, stagger: 0.1, ease: 'power3.out',
          scrollTrigger: { trigger: '.info-table', start: 'top 80%' }
        });
      }
    }

    // Video
    var videoFrame = document.querySelector('.video-content .video-frame');
    if (videoFrame) {
      gsap.fromTo(videoFrame, { scale: 0.88, opacity: 0 }, {
        scale: 1, opacity: 1, duration: 1.2, ease: 'power3.out',
        scrollTrigger: { trigger: '.video-content', start: 'top 80%' }
      });
    }

    // Fun facts
    var facts = document.querySelector('.fun-facts');
    if (facts) {
      var factCounters = facts.querySelectorAll('.counter');
      if (factCounters.length) {
        gsap.fromTo(factCounters, { y: 60, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.7, stagger: 0.2, ease: 'power3.out',
          scrollTrigger: { trigger: facts, start: 'top 75%' }
        });
      }
    }

    // Best deal
    var bestDeal = document.querySelector('.best-deal');
    if (bestDeal) {
      var dealHeading = bestDeal.querySelector('.section-heading');
      if (dealHeading) {
        gsap.fromTo(dealHeading, { y: 40, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.8, ease: 'power3.out',
          scrollTrigger: { trigger: bestDeal, start: 'top 80%' }
        });
      }
      var tabPanes = bestDeal.querySelectorAll('.tab-pane');
      if (tabPanes.length) {
        gsap.fromTo(tabPanes, { y: 50, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.8, ease: 'power3.out',
          scrollTrigger: { trigger: '.tabs-content', start: 'top 75%' }
        });
      }
    }

    // Property listings
    var propRow = document.querySelector('.properties .container > .row');
    if (propRow) {
      var propCards = propRow.querySelectorAll('.col-lg-4');
      if (propCards.length) {
        gsap.fromTo(propCards, { y: 80, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.7, stagger: 0.12, ease: 'power3.out',
          scrollTrigger: { trigger: propRow, start: 'top 80%' }
        });
      }
    }

  });

  // Mobile: lighter, faster animations
  mm.add('(max-width: 767px)', function () {

    var featured = document.querySelector('.featured');
    if (featured) {
      var heading = featured.querySelector('.section-heading');
      if (heading) {
        gsap.fromTo(heading, { y: 20, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.5,
          scrollTrigger: { trigger: featured, start: 'top 90%' }
        });
      }
      var accordionItems = featured.querySelectorAll('.accordion-item');
      if (accordionItems.length) {
        gsap.fromTo(accordionItems, { y: 15, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.4, stagger: 0.08,
          scrollTrigger: { trigger: '.accordion', start: 'top 90%' }
        });
      }
    }

    var facts = document.querySelector('.fun-facts');
    if (facts) {
      var factCounters = facts.querySelectorAll('.counter');
      if (factCounters.length) {
        gsap.fromTo(factCounters, { y: 20, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.4, stagger: 0.1,
          scrollTrigger: { trigger: facts, start: 'top 90%' }
        });
      }
    }

    // Properties cards: fast stagger, earlier trigger, smaller offset
    var propRow = document.querySelector('.properties .container > .row');
    if (propRow) {
      var propCards = propRow.querySelectorAll('.col-lg-4');
      if (propCards.length) {
        gsap.fromTo(propCards, { y: 25, opacity: 0 }, {
          y: 0, opacity: 1, duration: 0.4, stagger: 0.08,
          ease: 'power2.out',
          scrollTrigger: { trigger: propRow, start: 'top 90%' }
        });
      }
    }

  });

  ScrollTrigger.refresh();

  // Recalculate after all images and carousels are loaded
  window.addEventListener('load', function () {
    ScrollTrigger.refresh();
  });

  // Refresh on resize debounce (ScrollTrigger does this automatically, but a manual boost helps carousel layouts)
  setTimeout(function () { ScrollTrigger.refresh(); }, 500);

})();
