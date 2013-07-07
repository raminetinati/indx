describe('indx-core', function() {
	var injector = angular.injector(['ng','indx']), loggedin;
	var indx = injector.get('client'),
	    u = injector.get('utils'),
	    store = new indx.Store({server_host:"localhost:8211"}),
	    box;

	beforeEach(function() {
		var box_name = 'box-'+u.guid(12);
		box = undefined;
		store.login('webbox','webbox')		
			.then(function(x) {
				dump('login done ');
				loggedin = true;
				store.create_box(box_name).then(function(b) {
					box = store.get_box(box_name);
				});
				
			}).fail(function(x) {
				console.error('fail logging in ', x); loggedin = false;
			});
		waitsFor(function() { return loggedin === false || loggedin && box; });
	});

	it('box should be defined', function() {
		dump('box is', box);
		expect(box).toBeDefined();
	});

	// it('getinfo', function() {
	// 	var gi;
	// 	runs(function() {
	// 		store.getInfo()
	// 			.then(function(x) { dump('getinfo ', x); gi = x; })
	// 			.fail(function(x) { console.error('fail logging in ', x); });
	// 	});
	// 	waitsFor(function() { return gi; });
	// 	runs(function() {
	// 		expect(gi).toBeDefined();
	// 		dump('done waiting ', gi);	
	// 	});
	// });
	// it('should fetch boxes', function() {
	// 	var boxes;
	// 	runs(function() {
	// 		store.fetch()
	// 			.then(function(x) { dump('boxes ', x); boxes = store.boxes(); })
	// 			.fail(function(x) { console.error('fail logging in ', x); });
	// 	});
	// 	waitsFor(function() { return boxes; });
	// 	runs(function() {
	// 		dump('boxes >> ', boxes.map(function(x) { return x.get_id(); }));
	// 	});
	// });	
	
});
