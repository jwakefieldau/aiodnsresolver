import asyncio
import ipaddress
import unittest
from unittest.mock import (
    Mock,
    call,
)

from aiofastforward import (
    FastForward,
)

from aiodnsresolver import (
    TYPE_A,
    TYPE_AAAA,
    Resolver,
    memoize_ttl,
    timeout,
)


def async_test(func):
    def wrapper(*args, **kwargs):
        future = func(*args, **kwargs)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(future)
    return wrapper


def until_called(num_times):
    num_times_called = 0
    future = asyncio.Future()

    def func():
        nonlocal num_times_called
        num_times_called += 1
        if num_times_called == num_times:
            future.set_result(None)
        return future

    return func


class TestResolver(unittest.TestCase):

    @async_test
    async def test_a_query(self):
        resolve = Resolver()
        res = await resolve('www.google.com', TYPE_A)
        self.assertIsInstance(res, ipaddress.IPv4Address)

    @async_test
    async def test_a_query_multiple(self):
        resolve = Resolver()
        res = await resolve('charemza.name', TYPE_A)
        self.assertIsInstance(res, ipaddress.IPv4Address)

    @async_test
    async def test_a_query_twice_sequential(self):
        resolve = Resolver()
        res_a = await resolve('www.google.com', TYPE_A)
        self.assertIsInstance(res_a, ipaddress.IPv4Address)

        res_b = await resolve('www.google.com', TYPE_A)
        self.assertIsInstance(res_b, ipaddress.IPv4Address)

    @async_test
    async def test_a_query_twice_concurrent(self):
        resolve = Resolver()
        res_a = asyncio.ensure_future(resolve('www.google.com', TYPE_A))
        res_b = asyncio.ensure_future(resolve('www.google.com', TYPE_A))
        self.assertIsInstance(await res_a, ipaddress.IPv4Address)
        self.assertIsInstance(await res_b, ipaddress.IPv4Address)
        self.assertEqual(await res_a, await res_b)

    @async_test
    async def test_a_query_different_concurrent(self):
        resolve = Resolver()
        res_a = asyncio.ensure_future(resolve('www.google.com', TYPE_A))
        res_b = asyncio.ensure_future(resolve('charemza.name', TYPE_A))
        self.assertIsInstance(await res_a, ipaddress.IPv4Address)
        self.assertIsInstance(await res_b, ipaddress.IPv4Address)
        self.assertNotEqual(res_a, res_b)

    @async_test
    async def test_aaaa_query(self):
        resolve = Resolver()
        res = await resolve('www.google.com', TYPE_AAAA)
        self.assertIsInstance(res, ipaddress.IPv6Address)

    @async_test
    async def test_a_query_not_exists(self):
        resolve = Resolver()
        with self.assertRaises(Exception):
            res = await resolve('doenotexist.charemza.name', TYPE_A)

    @async_test
    async def test_aaaa_query_not_exists(self):
        resolve = Resolver()

        with self.assertRaises(Exception):
            res = await resolve('doenotexist.charemza.name', TYPE_AAAA)

    @async_test
    async def test_a_query_cname(self):
        resolve = Resolver()
        res = await resolve('support.dnsimple.com', TYPE_A)
        self.assertIsInstance(res, ipaddress.IPv4Address)


class TestMemoizeTtl(unittest.TestCase):

    @async_test
    async def test_identical_concurrent_memoized_coroutine(self):
        loop = asyncio.get_event_loop()
        mock = Mock()
        ttls = [2, 1]

        async def func(*args, **kwargs):
            mock(*args, **kwargs)
            # Allow to another task to run
            await asyncio.sleep(0)
            return 'value'

        memoized = memoize_ttl(func, lambda _: 100)

        task_a = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))
        task_b = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))

        task_a_result = await task_a
        task_b_result = await task_b
        self.assertEqual(task_a_result, 'value')
        self.assertEqual(task_b_result, 'value')
        self.assertEqual(mock.mock_calls, [call(10, 20, a='val_a', b='val_b')])

    @async_test
    async def test_identical_concurrent_memoized_future(self):
        loop = asyncio.get_event_loop()
        mock = Mock()
        future = asyncio.Future()

        def func(*args, **kwargs):
            mock(*args, **kwargs)
            return future

        memoized = memoize_ttl(func, lambda _: 100)

        task_a = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))
        task_b = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))

        await asyncio.sleep(0)
        future.set_result('value')

        task_a_result = await task_a
        task_b_result = await task_b
        self.assertEqual(task_a_result, 'value')
        self.assertEqual(task_b_result, 'value')
        self.assertEqual(mock.mock_calls, [call(10, 20, a='val_a', b='val_b')])

    @async_test
    async def test_different_concurrent_not_memoized(self):
        loop = asyncio.get_event_loop()
        mock = Mock()
        func_done = asyncio.Event()
        until_called_twice = until_called(num_times=2)

        async def func(*args, **kwargs):
            mock(*args, **kwargs)
            await until_called_twice()
            return kwargs['b']

        memoized = memoize_ttl(func, lambda _: 100)

        task_a = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b_a'))
        task_b = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b_b'))

        task_a_result = await task_a
        task_b_result = await task_b
        self.assertEqual(task_a_result, 'val_b_a')
        self.assertEqual(task_b_result, 'val_b_b')
        self.assertEqual(mock.mock_calls, [
            call(10, 20, a='val_a', b='val_b_a'),
            call(10, 20, a='val_a', b='val_b_b'),
        ])

    @async_test
    async def test_identical_sequential_memoized(self):
        loop = asyncio.get_event_loop()
        mock = Mock()
        results = ['b', 'a']

        async def func(*args, **kwargs):
            mock(*args, **kwargs)
            return results.pop()

        memoized = memoize_ttl(func, lambda _: 100)

        task_a = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))
        task_a_result = await task_a

        task_b = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))

        task_b_result = await task_b
        self.assertEqual(task_a_result, 'a')
        self.assertEqual(task_b_result, 'a')
        self.assertEqual(mock.mock_calls, [
            call(10, 20, a='val_a', b='val_b'),
        ])

    @async_test
    async def test_identical_sequential_invalidate(self):
        loop = asyncio.get_event_loop()
        mock = Mock()
        results = [4, 3, 2, 1]

        async def func(*args, **kwargs):
            mock(*args, **kwargs)
            return results.pop()

        with FastForward(loop) as forward:
            memoized = memoize_ttl(func, lambda result: result)

            task_a = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b_a'))
            task_b = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b_b'))
            task_a_result = await task_a
            task_b_result = await task_b

            await forward(1)
            task_c = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b_a'))
            task_d = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b_b'))
            task_c_result = await task_c
            task_d_result = await task_d

            self.assertEqual(task_c_result, 3)
            self.assertEqual(task_d_result, 2)
            self.assertEqual(mock.mock_calls, [
                call(10, 20, a='val_a', b='val_b_a'),
                call(10, 20, a='val_a', b='val_b_b'),
                call(10, 20, a='val_a', b='val_b_a'),
            ])

    @async_test
    async def test_identical_sequential_with_sleep_invalidate(self):
        loop = asyncio.get_event_loop()
        mock = Mock()
        results = [3, 2, 1]

        async def func(*args, **kwargs):
            await asyncio.sleep(0.5)
            mock(*args, **kwargs)
            return results.pop()

        with FastForward(loop) as forward:
            memoized = memoize_ttl(func, lambda result: result)

            forward(0.5)
            result_a = await memoized(10, 20, a='val_a', b='val_b')
            result_b = await memoized(10, 20, a='val_a', b='val_b')

            forward(1)
            result_c = await memoized(10, 20, a='val_a', b='val_b')

            self.assertEqual(result_a, 1)
            self.assertEqual(result_b, 1)
            self.assertEqual(result_c, 2)
            self.assertEqual(mock.mock_calls, [
                call(10, 20, a='val_a', b='val_b'),
                call(10, 20, a='val_a', b='val_b'),
            ])

    @async_test
    async def test_identical_concurrent_memoized_exception(self):
        loop = asyncio.get_event_loop()
        mock = Mock()
        results = ['b', 'a']

        async def func(*args, **kwargs):
            mock(*args, **kwargs)
            # Yield so the other task can run
            await asyncio.sleep(0)
            raise Exception(results.pop())

        memoized = memoize_ttl(func, lambda _: 100)

        task_a = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))
        task_b = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))

        with self.assertRaisesRegex(Exception, 'a'):
            await task_a

        with self.assertRaisesRegex(Exception, 'a'):
            await task_b

        self.assertEqual(mock.mock_calls, [call(10, 20, a='val_a', b='val_b')])

    @async_test
    async def test_identical_sequential_not_memoized_exception(self):
        loop = asyncio.get_event_loop()
        mock = Mock()
        results = ['b', 'a']

        async def func(*args, **kwargs):
            mock(*args, **kwargs)
            # Yield so the other task can run
            await asyncio.sleep(0)
            raise Exception(results.pop())

        memoized = memoize_ttl(func, lambda _: 100)

        task_a = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))

        with self.assertRaisesRegex(Exception, 'a'):
            await task_a

        task_b = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))

        with self.assertRaisesRegex(Exception, 'b'):
            await task_b

        self.assertEqual(mock.mock_calls, [
            call(10, 20, a='val_a', b='val_b'),
            call(10, 20, a='val_a', b='val_b'),
        ])

    @async_test
    async def test_identical_concurrent_memoized_cancelled(self):
        loop = asyncio.get_event_loop()
        mock = Mock()
        called = asyncio.Event()

        async def func(*args, **kwargs):
            mock(*args, **kwargs)
            called.set()
            await asyncio.Future()

        memoized = memoize_ttl(func, lambda _: 100)

        task_a = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))
        task_b = asyncio.ensure_future(memoized(10, 20, a='val_a', b='val_b'))
        await called.wait()
        task_a.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task_b



class TestTimeout(unittest.TestCase):

    @async_test
    async def test_shorter_than_timeout_not_raises(self):
            loop = asyncio.get_event_loop()

            async def worker():
                with timeout(1):
                    await asyncio.sleep(0.5)

            with FastForward(loop) as forward:
                task = asyncio.ensure_future(worker())

                await forward(0.5)
                await task

    @async_test
    async def test_longer_than_timeout_raises_timeout_error(self):
            loop = asyncio.get_event_loop()

            async def worker():
                with timeout(1):
                    await asyncio.sleep(1.5)

            with FastForward(loop) as forward:
                task = asyncio.ensure_future(worker())

                await forward(1)
                with self.assertRaises(asyncio.TimeoutError):
                    await task

    @async_test
    async def test_cancel_raises_cancelled_error(self):
            loop = asyncio.get_event_loop()

            async def worker():
                with timeout(1):
                    await asyncio.sleep(0.5)

            with FastForward(loop) as forward:
                task = asyncio.ensure_future(worker())

                await forward(0.25)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

    @async_test
    async def test_exception_propagates(self):
            loop = asyncio.get_event_loop()

            async def worker():
                with timeout(2):
                    raise Exception('inner')

            with FastForward(loop) as forward:
                task = asyncio.ensure_future(worker())

                await forward(1)
                with self.assertRaisesRegex(Exception, 'inner'):
                    await task

    @async_test
    async def test_cleanup(self):
            loop = asyncio.get_event_loop()
            cleanup = asyncio.Event()

            async def worker():
                with timeout(1):
                    try:
                        await asyncio.sleep(2)
                    except asyncio.CancelledError:
                        cleanup.set()
                        raise

            with FastForward(loop) as forward:
                task = asyncio.ensure_future(worker())

                await forward(1)
                with self.assertRaises(asyncio.TimeoutError):
                    await task

                self.assertTrue(cleanup.is_set())

    @async_test
    async def test_ignore_timeout(self):
            loop = asyncio.get_event_loop()
            ignored = asyncio.Event()

            async def worker():
                with timeout(1):
                    try:
                        await asyncio.sleep(2)
                    except asyncio.CancelledError:
                        # Swallow the exception
                        pass
                ignored.set()

            with FastForward(loop) as forward:
                task = asyncio.ensure_future(worker())

                await forward(1)
                await task
                self.assertTrue(ignored.is_set())
