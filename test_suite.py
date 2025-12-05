#!/usr/bin/env python3
"""
Test Suite for CLAUDE.md Prompt Optimization System

Run with: python test_suite.py
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from pathlib import Path
from io import StringIO


# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prompt_splitter import PromptSplitter, Priority, Section
from prompt_loader import (
    PromptLoader,
    CachedPromptLoader,
    LoadContext,
    ContextPresets
)
from prompt_integration import OptimizedPromptService


class TestPromptSplitter(unittest.TestCase):
    """Tests for the PromptSplitter class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = tempfile.mkdtemp()
        self.splitter = PromptSplitter(min_section_chars=10)

    def tearDown(self):
        """Clean up test files."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_basic_split(self):
        """Test basic file splitting."""
        content = """# Core Identity

You are an AI assistant.

## Safety Guidelines

Always be helpful and harmless.

## Tool Usage

Use tools responsibly.
"""
        # Write test file
        input_file = os.path.join(self.test_dir, 'test.md')
        with open(input_file, 'w') as f:
            f.write(content)

        # Split
        output_dir = os.path.join(self.test_dir, 'output')
        result = self.splitter.split_file(input_file, output_dir)

        # Verify
        self.assertGreater(result.total_sections, 0)
        self.assertTrue(os.path.exists(result.manifest_path))

    def test_section_id_generation(self):
        """Test section ID generation from titles."""
        test_cases = [
            ("Core Identity", "core_identity"),
            ("Tool Usage Guidelines", "tool_usage_guidelines"),
            ("Special & Chars!", "special_chars"),  # Special chars get removed
        ]

        for title, expected in test_cases:
            section_id = self.splitter._generate_section_id(title)
            self.assertEqual(
                section_id, expected,
                f"Expected '{expected}' but got '{section_id}'"
            )

    def test_priority_classification(self):
        """Test priority classification of sections."""
        sections = [
            Section(id="core", title="Core Identity", content="core essential", priority=Priority.CONDITIONAL),
            Section(id="tools", title="Tool Usage", content="conditional tool", priority=Priority.CONDITIONAL),
            Section(id="advanced", title="Advanced", content="optional rarely used", priority=Priority.CONDITIONAL),
        ]

        classified = self.splitter._classify_priorities(sections)

        self.assertEqual(classified[0].priority, Priority.CORE)  # First section = core

    def test_capability_detection(self):
        """Test capability detection in sections."""
        sections = [
            Section(id="tools", title="Tools", content="Use the tool function to call APIs", priority=Priority.CONDITIONAL),
            Section(id="memory", title="Context", content="Remember and recall previous context", priority=Priority.CONDITIONAL),
        ]

        detected = self.splitter._detect_capabilities(sections)

        self.assertIn('tools', detected[0].capabilities)
        self.assertIn('memory', detected[1].capabilities)

    def test_manifest_generation(self):
        """Test manifest.json generation."""
        content = "# Test\n\nTest content here."
        input_file = os.path.join(self.test_dir, 'test.md')
        with open(input_file, 'w') as f:
            f.write(content)

        output_dir = os.path.join(self.test_dir, 'output')
        result = self.splitter.split_file(input_file, output_dir)

        # Check manifest exists and is valid JSON
        with open(result.manifest_path) as f:
            manifest = json.load(f)

        self.assertIn('version', manifest)
        self.assertIn('sections', manifest)
        self.assertIn('total_sections', manifest)


class TestPromptLoader(unittest.TestCase):
    """Tests for the PromptLoader class."""

    @classmethod
    def setUpClass(cls):
        """Create test prompts directory."""
        cls.test_dir = tempfile.mkdtemp()
        cls._create_test_prompts(cls.test_dir)

    @classmethod
    def tearDownClass(cls):
        """Clean up test files."""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    @classmethod
    def _create_test_prompts(cls, base_dir):
        """Create a test prompt structure."""
        # Create directories
        os.makedirs(os.path.join(base_dir, 'core'), exist_ok=True)
        os.makedirs(os.path.join(base_dir, 'conditional'), exist_ok=True)
        os.makedirs(os.path.join(base_dir, 'optional'), exist_ok=True)

        # Create core section
        with open(os.path.join(base_dir, 'core', 'identity.md'), 'w') as f:
            f.write("# Core Identity\n\nYou are an AI assistant.")

        # Create conditional sections
        with open(os.path.join(base_dir, 'conditional', 'tools.md'), 'w') as f:
            f.write("# Tool Usage\n\nUse tools responsibly.")

        with open(os.path.join(base_dir, 'conditional', 'memory.md'), 'w') as f:
            f.write("# Memory\n\nRemember context.")

        # Create optional section
        with open(os.path.join(base_dir, 'optional', 'advanced.md'), 'w') as f:
            f.write("# Advanced\n\nAdvanced features.")

        # Create manifest
        manifest = {
            "version": "1.0",
            "source_file": "test.md",
            "total_sections": 4,
            "total_characters": 200,
            "sections": [
                {
                    "id": "identity",
                    "title": "Core Identity",
                    "priority": "core",
                    "capabilities": ["identity"],
                    "dependencies": [],
                    "char_count": 50,
                    "file": "core/identity.md"
                },
                {
                    "id": "tools",
                    "title": "Tool Usage",
                    "priority": "conditional",
                    "capabilities": ["tools"],
                    "dependencies": [],
                    "char_count": 50,
                    "file": "conditional/tools.md"
                },
                {
                    "id": "memory",
                    "title": "Memory",
                    "priority": "conditional",
                    "capabilities": ["memory"],
                    "dependencies": [],
                    "char_count": 50,
                    "file": "conditional/memory.md"
                },
                {
                    "id": "advanced",
                    "title": "Advanced",
                    "priority": "optional",
                    "capabilities": [],
                    "dependencies": [],
                    "char_count": 50,
                    "file": "optional/advanced.md"
                }
            ]
        }

        with open(os.path.join(base_dir, 'manifest.json'), 'w') as f:
            json.dump(manifest, f)

    def test_load_manifest(self):
        """Test manifest loading."""
        loader = PromptLoader(self.test_dir)
        self.assertEqual(loader.manifest['total_sections'], 4)

    def test_minimal_context(self):
        """Test minimal context loads only core."""
        loader = PromptLoader(self.test_dir)
        context = ContextPresets.minimal()
        result = loader.load_prompt(context)

        self.assertIn('identity', result.sections_loaded)
        self.assertLess(result.total_sections, 4)

    def test_tool_context(self):
        """Test tool context loads tools section."""
        loader = PromptLoader(self.test_dir)
        context = ContextPresets.tool_use()
        result = loader.load_prompt(context)

        self.assertIn('identity', result.sections_loaded)
        self.assertIn('tools', result.sections_loaded)

    def test_full_context(self):
        """Test full context loads everything including optional."""
        loader = PromptLoader(self.test_dir)
        context = ContextPresets.full()
        result = loader.load_prompt(context)

        # Should load at least core + some conditional sections
        self.assertGreaterEqual(result.total_sections, 3)

    def test_get_section(self):
        """Test getting individual sections."""
        loader = PromptLoader(self.test_dir)
        content = loader.get_section('identity')

        self.assertIsNotNone(content)
        self.assertIn('Core Identity', content)

    def test_list_sections(self):
        """Test listing all sections."""
        loader = PromptLoader(self.test_dir)
        sections = loader.list_sections()

        self.assertEqual(len(sections), 4)

    def test_get_stats(self):
        """Test getting statistics."""
        loader = PromptLoader(self.test_dir)
        stats = loader.get_stats()

        self.assertEqual(stats['total_sections'], 4)
        self.assertIn('by_priority', stats)


class TestCachedPromptLoader(unittest.TestCase):
    """Tests for the CachedPromptLoader class."""

    @classmethod
    def setUpClass(cls):
        """Create test prompts directory."""
        cls.test_dir = tempfile.mkdtemp()
        TestPromptLoader._create_test_prompts(cls.test_dir)

    @classmethod
    def tearDownClass(cls):
        """Clean up test files."""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_cache_hit(self):
        """Test that repeated loads hit the cache."""
        loader = CachedPromptLoader(self.test_dir, cache_size=10)
        context = ContextPresets.conversational()

        # First load - cache miss
        loader.load_prompt(context)
        stats = loader.get_cache_stats()
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['hits'], 0)

        # Second load - cache hit
        loader.load_prompt(context)
        stats = loader.get_cache_stats()
        self.assertEqual(stats['hits'], 1)

    def test_cache_clear(self):
        """Test cache clearing."""
        loader = CachedPromptLoader(self.test_dir)
        context = ContextPresets.minimal()

        loader.load_prompt(context)
        self.assertEqual(loader.get_cache_stats()['cached_prompts'], 1)

        loader.clear_cache()
        self.assertEqual(loader.get_cache_stats()['cached_prompts'], 0)

    def test_cache_eviction(self):
        """Test cache eviction when full."""
        loader = CachedPromptLoader(self.test_dir, cache_size=2)

        # Load 3 different contexts
        contexts = [
            ContextPresets.minimal(),
            ContextPresets.conversational(),
            ContextPresets.tool_use()
        ]

        for ctx in contexts:
            loader.load_prompt(ctx)

        # Cache should have at most 2 entries
        self.assertLessEqual(loader.get_cache_stats()['cached_prompts'], 2)


class TestOptimizedPromptService(unittest.TestCase):
    """Tests for the OptimizedPromptService class."""

    @classmethod
    def setUpClass(cls):
        """Create test prompts directory."""
        cls.test_dir = tempfile.mkdtemp()
        TestPromptLoader._create_test_prompts(cls.test_dir)

    @classmethod
    def tearDownClass(cls):
        """Clean up test files."""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_get_system_prompt(self):
        """Test getting system prompt."""
        service = OptimizedPromptService(self.test_dir)
        context = ContextPresets.conversational()

        prompt = service.get_system_prompt(context)

        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 0)

    def test_get_prompt_with_metadata(self):
        """Test getting prompt with metadata."""
        service = OptimizedPromptService(self.test_dir)
        context = ContextPresets.tool_use()

        result = service.get_prompt_with_metadata(context)

        self.assertIn('content', result)
        self.assertIn('sections', result)
        self.assertIn('char_count', result)
        self.assertIn('cache_hit', result)

    def test_performance_stats(self):
        """Test performance statistics."""
        service = OptimizedPromptService(self.test_dir)

        # Make some requests
        for _ in range(3):
            service.get_system_prompt(ContextPresets.minimal())

        stats = service.get_performance_stats()

        self.assertEqual(stats['total_requests'], 3)
        self.assertIn('cache_stats', stats)
        self.assertGreater(stats['cache_stats']['hit_rate'], 0)

    def test_cache_warming(self):
        """Test cache warming."""
        service = OptimizedPromptService(self.test_dir)

        service.warm_cache()

        stats = service.get_performance_stats()
        self.assertGreater(stats['cache_stats']['entries'], 0)

    def test_cache_disabled(self):
        """Test with cache disabled."""
        service = OptimizedPromptService(self.test_dir, enable_cache=False)
        context = ContextPresets.minimal()

        # Multiple loads should all be misses
        for _ in range(3):
            service.get_system_prompt(context)

        stats = service.get_performance_stats()
        self.assertEqual(stats['cache_stats']['hits'], 0)


class TestContextPresets(unittest.TestCase):
    """Tests for context presets."""

    def test_all_presets_create_valid_context(self):
        """Test that all presets create valid LoadContext objects."""
        presets = [
            ContextPresets.minimal(),
            ContextPresets.conversational(),
            ContextPresets.mortgage_crm(),
            ContextPresets.tool_use(),
            ContextPresets.agent_orchestration(),
            ContextPresets.full()
        ]

        for preset in presets:
            self.assertIsInstance(preset, LoadContext)
            self.assertIsInstance(preset.to_cache_key(), str)

    def test_cache_keys_unique(self):
        """Test that different presets have unique cache keys."""
        presets = [
            ContextPresets.minimal(),
            ContextPresets.conversational(),
            ContextPresets.mortgage_crm(),
            ContextPresets.tool_use(),
            ContextPresets.agent_orchestration(),
            ContextPresets.full()
        ]

        keys = [p.to_cache_key() for p in presets]
        self.assertEqual(len(keys), len(set(keys)), "Cache keys should be unique")


class TestEndToEnd(unittest.TestCase):
    """End-to-end integration tests."""

    def test_split_and_load_workflow(self):
        """Test the complete split and load workflow."""
        # Create temp directory
        test_dir = tempfile.mkdtemp()

        try:
            # Create a test CLAUDE.md
            input_file = os.path.join(test_dir, 'CLAUDE.md')
            with open(input_file, 'w') as f:
                f.write("""# Core Identity

You are Perennia AI, a mortgage assistant.

## Safety Guidelines

Always protect borrower information.

## Tool Usage

Use tools to help loan officers.

## Memory

Remember conversation context.
""")

            # Split the file
            splitter = PromptSplitter(min_section_chars=10)
            output_dir = os.path.join(test_dir, 'prompts')
            split_result = splitter.split_file(input_file, output_dir)

            self.assertGreater(split_result.total_sections, 0)

            # Load prompts
            service = OptimizedPromptService(output_dir)

            # Test different contexts
            for context in [ContextPresets.minimal(), ContextPresets.full()]:
                prompt = service.get_system_prompt(context)
                self.assertGreater(len(prompt), 0)

            # Verify reduction
            stats = service.get_performance_stats()
            self.assertGreater(stats['original_prompt_chars'], 0)

        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


class TestPerformanceBenchmark(unittest.TestCase):
    """Performance benchmark tests."""

    @classmethod
    def setUpClass(cls):
        """Create test prompts directory."""
        cls.test_dir = tempfile.mkdtemp()
        TestPromptLoader._create_test_prompts(cls.test_dir)

    @classmethod
    def tearDownClass(cls):
        """Clean up test files."""
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_load_performance(self):
        """Test load performance is acceptable."""
        service = OptimizedPromptService(self.test_dir)

        # Warm up
        service.get_system_prompt(ContextPresets.minimal())

        # Benchmark
        iterations = 100
        start = time.time()

        for _ in range(iterations):
            service.get_system_prompt(ContextPresets.conversational())

        elapsed = time.time() - start
        avg_time_ms = (elapsed / iterations) * 1000

        # Should be under 10ms per load with cache
        self.assertLess(avg_time_ms, 10, f"Average load time {avg_time_ms:.2f}ms exceeds threshold")

    def test_cache_hit_rate(self):
        """Test cache hit rate is acceptable."""
        service = OptimizedPromptService(self.test_dir)

        contexts = [
            ContextPresets.minimal(),
            ContextPresets.conversational(),
            ContextPresets.tool_use()
        ]

        # Make requests
        for _ in range(10):
            for ctx in contexts:
                service.get_system_prompt(ctx)

        stats = service.get_performance_stats()

        # Hit rate should be > 70% after initial misses
        self.assertGreater(stats['cache_stats']['hit_rate'], 70)


def run_tests():
    """Run all tests with summary."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    test_classes = [
        TestPromptSplitter,
        TestPromptLoader,
        TestCachedPromptLoader,
        TestOptimizedPromptService,
        TestContextPresets,
        TestEndToEnd,
        TestPerformanceBenchmark
    ]

    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    # Run tests
    print("=" * 70)
    print("CLAUDE.md Optimization System - Test Suite")
    print("=" * 70)
    print()

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print()

    if result.wasSuccessful():
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == '__main__':
    sys.exit(run_tests())
