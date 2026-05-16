"""
Test cases for the arize-ai-provider-integration skill.

Verifies that Claude can list, create, update, and delete AI integrations
(LLM provider credentials) using the ax CLI.
"""

import pytest

from conftest import make_runner
from harness.verifier import (
    BashCommandContainsVerifier,
    CompositeVerifier,
    NoErrorVerifier,
    OutputContainsVerifier,
)


@pytest.fixture
def integration_runner(workspace, arize_env, test_model):
    return make_runner(
        "arize-ai-provider-integration", workspace, arize_env, test_model
    )


class TestIntegrationList:
    """User asks to list existing AI integrations."""

    @pytest.mark.asyncio
    async def test_list_integrations(
        self, integration_runner, test_report, arize_space_id
    ):
        result = await integration_runner.run(
            f"List all AI integrations in space {arize_space_id}."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax ai-integrations list"]),
            OutputContainsVerifier(["integration"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed

    @pytest.mark.asyncio
    async def test_list_integrations_json(
        self, integration_runner, test_report, arize_space_id
    ):
        result = await integration_runner.run(
            f"List all AI integrations in space {arize_space_id} in JSON format "
            f"and tell me the provider and name of each one."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax ai-integrations list"]),
            OutputContainsVerifier(["integration", "provider"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestIntegrationCreateOpenAI:
    """User asks to create an OpenAI integration."""

    @pytest.mark.asyncio
    async def test_create_openai_integration_guide(
        self, integration_runner, test_report, arize_space_id
    ):
        result = await integration_runner.run(
            f"I want to create an OpenAI integration called 'test-openai-guide' "
            f"for my evaluators. Walk me through the command I need to run "
            f"(use a placeholder for the API key)."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            OutputContainsVerifier(["ax ai-integrations create", "openAI"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestIntegrationCreateAnthropic:
    """User asks to create an Anthropic integration."""

    @pytest.mark.asyncio
    async def test_create_anthropic_integration_guide(
        self, integration_runner, test_report, arize_space_id
    ):
        result = await integration_runner.run(
            f"How do I create an Anthropic AI integration in space {arize_space_id}? "
            f"Show me the exact command."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            OutputContainsVerifier(["ax ai-integrations create", "anthropic"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestIntegrationGet:
    """User asks to inspect a specific integration."""

    @pytest.mark.asyncio
    async def test_get_integration_by_listing_first(
        self, integration_runner, test_report, arize_space_id
    ):
        result = await integration_runner.run(
            f"List the AI integrations in space {arize_space_id} and show me "
            f"the details of the first one you find."
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            BashCommandContainsVerifier(["ax ai-integrations"]),
            OutputContainsVerifier(["integration"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed


class TestIntegrationProviderVariants:
    """User asks about creating integrations for non-OpenAI providers."""

    @pytest.mark.asyncio
    async def test_bedrock_integration_guidance(
        self, integration_runner, test_report, arize_space_id
    ):
        result = await integration_runner.run(
            f"I use AWS Bedrock. How do I set up an AI integration for it "
            f"in space {arize_space_id}? What flags do I need?"
        )
        verifier = CompositeVerifier(
            NoErrorVerifier(),
            OutputContainsVerifier(["awsBedrock", "role_arn"]),
        )
        result.verification = verifier.verify(result)
        test_report.add(result)
        assert result.passed
